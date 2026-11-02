# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class IberinformBulkUpdateWizard(models.TransientModel):
    _name = "iberinform.bulk.update.wizard"
    _description = "Criar fila de atualizações Iberinform + SICAE"

    line_ids = fields.One2many("iberinform.bulk.update.wizard.line", "wizard_id", string="Empresas")
    selected_count = fields.Integer(string="Empresas selecionadas", compute="_compute_selected_count")
    batch_size = fields.Selection([
        ("1", "1 empresa por lote (recomendado)"),
        ("2", "2 empresas por lote"),
        ("3", "3 empresas por lote"),
    ], string="Dimensão do lote", default="1", required=True)

    @api.depends("line_ids.selected")
    def _compute_selected_count(self):
        for wizard in self:
            wizard.selected_count = len(wizard.line_ids.filtered("selected"))

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        partners = self.env["res.partner"].search([
            ("is_company", "=", True), ("active", "=", True),
        ], order="name, id")
        eligible = partners.filtered(lambda p: bool(p._normalize_nif(p.vat)))
        values["line_ids"] = [
            (0, 0, {"selected": True, "partner_id": p.id, "vat": p.vat or False})
            for p in eligible
        ]
        return values

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_select_all(self):
        self.ensure_one()
        self.line_ids.write({"selected": True})
        return self._reopen()

    def action_deselect_all(self):
        self.ensure_one()
        self.line_ids.write({"selected": False})
        return self._reopen()

    def action_confirm(self):
        self.ensure_one()
        selected_lines = self.line_ids.filtered("selected")
        if not selected_lines:
            raise UserError(_("Selecione pelo menos uma empresa para atualizar."))

        Job = self.env["iberinform.bulk.job"]
        # Evitar uma segunda fila que ignore um bloqueio já detetado.
        ongoing = Job.search([("state", "in", ["queued", "paused"])], limit=1)
        if ongoing:
            raise UserError(_(
                "Já existe uma fila Iberinform em curso ou pausada (ID %s). "
                "Abra o histórico de atualizações e conclua ou resolva essa fila "
                "antes de iniciar outra."
            ) % ongoing.id)

        job = Job.create({
            "name": _("Consulta pública — %s empresas") % len(selected_lines),
            "batch_size": self.batch_size,
            "line_ids": [(0, 0, {
                "partner_id": line.partner_id.id,
                "vat": line.vat,
            }) for line in selected_lines],
        })
        job._wake_cron()
        return job.action_refresh()


class IberinformBulkUpdateWizardLine(models.TransientModel):
    _name = "iberinform.bulk.update.wizard.line"
    _description = "Empresa a atualizar Iberinform + SICAE"
    _order = "partner_name, id"

    wizard_id = fields.Many2one("iberinform.bulk.update.wizard", required=True, ondelete="cascade")
    selected = fields.Boolean(string="Atualizar", default=True)
    partner_id = fields.Many2one("res.partner", string="Empresa", required=True, readonly=True)
    partner_name = fields.Char(related="partner_id.name", string="Empresa", readonly=True, store=False)
    vat = fields.Char(string="NIF/NIPC", readonly=True)
