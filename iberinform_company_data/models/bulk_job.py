# -*- coding: utf-8 -*-
"""Fila persistente e conservadora para consultas públicas autorizadas.

Não contorna bloqueios HTTP: ao receber 403/429 interrompe-se e exige
intervenção humana. Nenhum pedido é feito durante a pausa.
"""
import logging
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Intervalo entre LOTES (não entre execuções da cron propriamente dita).
_MINUTES_BETWEEN_BATCHES = 15


class IberinformBulkJob(models.Model):
    _name = "iberinform.bulk.job"
    _description = "Fila de atualização Iberinform + SICAE"
    _order = "create_date desc, id desc"

    name = fields.Char(string="Lote", required=True, readonly=True, default="Atualização Iberinform")
    requested_by = fields.Many2one("res.users", string="Iniciado por", readonly=True,
                                   required=True, default=lambda self: self.env.user)
    state = fields.Selection([
        ("queued", "Em curso"),
        ("paused", "Pausado por bloqueio do fornecedor"),
        ("done", "Concluído"),
        ("cancelled", "Cancelado"),
    ], string="Estado", default="queued", required=True, readonly=True, index=True)
    batch_size = fields.Selection([
        ("1", "1 empresa por lote"),
        ("2", "2 empresas por lote"),
        ("3", "3 empresas por lote"),
    ], string="Empresas por lote", default="1", readonly=True, required=True)
    line_ids = fields.One2many("iberinform.bulk.job.line", "job_id", string="Empresas", readonly=True)
    next_run_at = fields.Datetime(string="Próximo lote a partir de", readonly=True, default=fields.Datetime.now, index=True)
    last_batch_at = fields.Datetime(string="Último lote", readonly=True)
    last_error = fields.Text(string="Último bloqueio", readonly=True)
    total_count = fields.Integer(string="Total", compute="_compute_counts")
    completed_count = fields.Integer(string="Concluídas", compute="_compute_counts")
    partial_count = fields.Integer(string="Parciais", compute="_compute_counts")
    failed_count = fields.Integer(string="Falhas", compute="_compute_counts")
    blocked_count = fields.Integer(string="Bloqueadas", compute="_compute_counts")
    pending_count = fields.Integer(string="Pendentes", compute="_compute_counts")

    @api.depends("line_ids.state")
    def _compute_counts(self):
        for job in self:
            states = job.line_ids.mapped("state")
            job.total_count = len(states)
            job.completed_count = states.count("success")
            job.partial_count = states.count("partial")
            job.failed_count = states.count("failed")
            job.blocked_count = states.count("blocked")
            job.pending_count = states.count("pending")

    @api.model
    def _wake_cron(self):
        cron = self.env.ref("iberinform_company_data.ir_cron_iberinform_bulk", raise_if_not_found=False)
        if cron and cron.active:
            cron.sudo()._trigger()

    def action_refresh(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Estado da atualização Iberinform"),
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_cancel(self):
        for job in self.filtered(lambda j: j.state in ("queued", "paused")):
            job.write({"state": "cancelled"})
        return self.action_refresh()

    def action_resume(self):
        self.ensure_one()
        if self.state != "paused":
            raise UserError(_("Esta fila não está pausada."))
        # Uma pausa 403/429 só pode ser retomada MANUALMENTE. Confirme com
        # o fornecedor que o acesso está autorizado antes de retomar.
        self.line_ids.filtered(lambda line: line.state == "blocked").write({
            "state": "pending", "error": False,
        })
        self.write({
            "state": "queued",
            "last_error": False,
            "next_run_at": fields.Datetime.now(),
        })
        self._wake_cron()
        return self.action_refresh()

    def _format_local_next_run(self):
        """Hora de Portugal/do utilizador, em vez do datetime UTC cru da BD.

        O Odoo armazena Datetime em UTC e o widget da vista faz a conversão
        automaticamente. Nas mensagens de Python a conversão é explícita.
        """
        self.ensure_one()
        if not self.next_run_at:
            return _("não definida")
        utc_naive = fields.Datetime.to_datetime(self.next_run_at)
        local = fields.Datetime.context_timestamp(self, utc_naive)
        return "%s (%s)" % (
            local.strftime("%d/%m/%Y %H:%M:%S"),
            local.strftime("%Z") or (self.env.user.tz or "UTC"),
        )

    def action_run_one_batch(self):
        """Executa só se elegível; caso contrário avisa e atualiza a ficha.

        A cron pode avançar next_run_at após a ficha ter sido carregada.
        Um UserError deixava o ecrã desatualizado e mostrava a hora UTC crua.
        """
        self.ensure_one()
        if self.state != "queued":
            raise UserError(_("A fila não está ativa."))
        now = fields.Datetime.now()
        if self.next_run_at and self.next_run_at > now:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Lote ainda não disponível"),
                    "message": _(
                        "O próximo lote ficará disponível a partir de %s. "
                        "O horário segue o fuso das suas Preferências."
                    ) % self._format_local_next_run(),
                    "type": "warning",
                    "sticky": False,
                    # Reabre a ficha para reler a data e as contagens atuais.
                    "next": self.action_refresh(),
                },
            }
        self._process_one_batch()
        return self.action_refresh()

    def _process_one_batch(self):
        self.ensure_one()
        # A cron e o botão manual podem coincidir. Tenta obter um lock
        # sem espera, para nunca executar simultaneamente duas consultas.
        job = self.try_lock_for_update().filtered_domain([("state", "=", "queued")])
        if not job:
            return 0
        now = fields.Datetime.now()
        if job.next_run_at and job.next_run_at > now:
            return 0
        pending = job.line_ids.filtered(lambda line: line.state == "pending")
        if not pending:
            job.write({"state": "done"})
            return 0
        subset = pending[:int(job.batch_size)]
        processed = 0
        blocked = False
        for line in subset:
            processed += 1
            partner = line.partner_id
            try:
                # Ao falhar uma consulta, só a empresa atual é revertida.
                with self.env.cr.savepoint():
                    action = partner.with_context(
                        iberinform_bulk_stop_on_denial=True,
                    ).action_get_iberinform_data()
                result_type = action.get("params", {}).get("type") if isinstance(action, dict) else None
                line.write({
                    "state": "success" if result_type == "success" else "partial",
                    "error": False,
                    "processed_at": fields.Datetime.now(),
                })
            except requests.HTTPError as exc:
                response = getattr(exc, "response", None)
                status_code = response.status_code if response is not None else None
                if status_code in (403, 429):
                    source_url = (getattr(response, "url", None) or "")
                    source_host = source_url.split("/")[2] if "://" in source_url else "fornecedor"
                    reason = _(
                        "HTTP %(code)s devolvido por %(host)s. As consultas foram "
                        "interrompidas; confirme com o fornecedor o acesso autorizado "
                        "antes de retomar manualmente."
                    ) % {"code": status_code, "host": source_host}
                    line.write({"state": "blocked", "error": reason,
                                "processed_at": fields.Datetime.now()})
                    job.write({"state": "paused", "last_error": reason})
                    _logger.warning("Fila Iberinform %s suspensa: %s", job.id, reason)
                    blocked = True
                    break
                line.write({"state": "failed", "error": str(exc)[:1000],
                            "processed_at": fields.Datetime.now()})
                _logger.warning("Falha HTTP no lote %s, contacto %s: %s", job.id, partner.id, exc)
            except Exception as exc:
                line.write({"state": "failed", "error": str(exc)[:1000],
                            "processed_at": fields.Datetime.now()})
                _logger.exception("Falha na consulta em lote %s, contacto %s", job.id, partner.id)

        job.write({
            "last_batch_at": fields.Datetime.now(),
            "next_run_at": fields.Datetime.now() + timedelta(minutes=_MINUTES_BETWEEN_BATCHES),
        })
        if not blocked and not job.line_ids.filtered(lambda line: line.state == "pending"):
            job.write({"state": "done"})
        return processed

    @api.model
    def _cron_process_iberinform_bulk(self):
        """No máximo UM pequeno lote por invocação da tarefa agendada.

        remaining=0 informa o scheduler Odoo 19 para não acelerar lotes
        sucessivos na mesma invocação.
        """
        job = self.search([
            ("state", "=", "queued"),
            ("next_run_at", "<=", fields.Datetime.now()),
        ], order="create_date, id", limit=1)
        processed = job._process_one_batch() if job else 0
        self.env["ir.cron"]._commit_progress(processed, remaining=0)


class IberinformBulkJobLine(models.Model):
    _name = "iberinform.bulk.job.line"
    _description = "Linha de fila Iberinform"
    _order = "id"

    job_id = fields.Many2one("iberinform.bulk.job", string="Fila", required=True,
                             ondelete="cascade", index=True)
    partner_id = fields.Many2one("res.partner", string="Empresa", required=True,
                                 readonly=True, ondelete="cascade")
    vat = fields.Char(string="NIF/NIPC", readonly=True)
    state = fields.Selection([
        ("pending", "Pendente"),
        ("success", "Completa"),
        ("partial", "Parcial"),
        ("failed", "Falha"),
        ("blocked", "Bloqueada (403/429)"),
    ], string="Estado", default="pending", required=True, index=True, readonly=True)
    processed_at = fields.Datetime(string="Processada em", readonly=True)
    error = fields.Text(string="Detalhe", readonly=True)

    _unique_partner_per_job = models.Constraint(
        "UNIQUE(job_id, partner_id)",
        "Não é possível repetir uma empresa na mesma fila.",
    )
