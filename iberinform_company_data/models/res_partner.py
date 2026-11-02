import json
import logging
import re
import unicodedata
from datetime import datetime
from urllib.parse import urljoin

import requests
from lxml import html

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Iberinform
    iberinform_url = fields.Char(string="URL Iberinform", readonly=True, copy=False)
    iberinform_last_sync = fields.Datetime(string="Última atualização Iberinform", readonly=True, copy=False)
    iberinform_legal_form = fields.Char(string="Forma jurídica", readonly=True, copy=False)
    iberinform_municipality = fields.Char(string="Concelho", readonly=True, copy=False)
    iberinform_cae_code = fields.Char(string="CAE principal Iberinform", readonly=True, copy=False)
    iberinform_cae_description = fields.Char(string="Descrição CAE", readonly=True, copy=False)
    iberinform_sector = fields.Char(string="Setor", readonly=True, copy=False)
    iberinform_constitution_date = fields.Date(string="Data de constituição", readonly=True, copy=False)
    iberinform_turnover = fields.Char(string="Volume de negócios", readonly=True, copy=False)
    iberinform_share_capital = fields.Char(string="Capital social", readonly=True, copy=False)
    iberinform_turnover_evolution = fields.Char(string="Evolução do volume de negócios", readonly=True, copy=False)
    iberinform_company_size = fields.Selection(
        selection=[
            ("Micro", "Micro"),
            ("Pequena", "Pequena"),
            ("Média", "Média"),
            ("Grande", "Grande"),
        ],
        string="Dimensão da empresa",
        copy=False,
    )
    iberinform_employees = fields.Char(string="Empregados", readonly=True, copy=False)

    # Dados originais devolvidos pela Iberinform. São campos calculados NÃO
    # armazenados em res_partner: a persistência é feita no modelo auxiliar
    # iberinform.public.snapshot, para evitar novas colunas na tabela de
    # contactos e permitir atualizar o código antes do upgrade do módulo.
    iberinform_source_name = fields.Char(
        string="Nome na Iberinform", compute="_compute_iberinform_source", readonly=True
    )
    iberinform_source_vat = fields.Char(
        string="NIF/NIPC na Iberinform", compute="_compute_iberinform_source", readonly=True
    )
    iberinform_source_address = fields.Char(
        string="Morada original na Iberinform", compute="_compute_iberinform_source", readonly=True
    )
    iberinform_source_street = fields.Char(
        string="Rua na Iberinform", compute="_compute_iberinform_source", readonly=True
    )
    iberinform_source_zip = fields.Char(
        string="Código postal na Iberinform", compute="_compute_iberinform_source", readonly=True
    )
    iberinform_source_city = fields.Char(
        string="Localidade na Iberinform", compute="_compute_iberinform_source", readonly=True
    )
    iberinform_source_district = fields.Char(
        string="Distrito na Iberinform", compute="_compute_iberinform_source", readonly=True
    )
    iberinform_source_country_code = fields.Char(
        string="País na Iberinform (código)", compute="_compute_iberinform_source", readonly=True
    )
    iberinform_source_company_size = fields.Char(
        string="Dimensão original na Iberinform", compute="_compute_iberinform_source", readonly=True
    )

    _IBERINFORM_SOURCE_FIELDS = (
        "name", "vat", "address", "street", "zip", "city",
        "district", "country_code", "company_size",
    )

    @api.depends("iberinform_last_sync")
    def _compute_iberinform_source(self):
        """Mostra o último valor público; nunca precisa de colunas no contacto.

        Durante uma troca de código, o Odoo pode arrancar antes do upgrade.
        Nesse intervalo, a tabela auxiliar ainda não existe: mostrar valores
        vazios em vez de causar UndefinedTable num formulário de contactos.
        """
        records_by_partner = {}
        if self.ids:
            self.env.cr.execute("SELECT to_regclass(%s)", ("iberinform_public_snapshot",))
            if self.env.cr.fetchone()[0]:
                snapshots = self.env["iberinform.public.snapshot"].sudo().search([
                    ("partner_id", "in", self.ids),
                ])
                records_by_partner = {snap.partner_id.id: snap for snap in snapshots}
        for partner in self:
            source = records_by_partner.get(partner.id)
            for source_field in self._IBERINFORM_SOURCE_FIELDS:
                partner["iberinform_source_" + source_field] = (
                    source[source_field] if source else False
                )

    def _iberinform_update_source_snapshot(self, data):
        """Guarda a resposta pública separadamente, sem alterar dados manuais."""
        self.ensure_one()
        Snapshot = self.env["iberinform.public.snapshot"].sudo()
        values = {
            "name": data.get("name") or False,
            "vat": data.get("vat") or False,
            "address": data.get("raw_address") or False,
            "street": data.get("street") or False,
            "zip": data.get("zip") or False,
            "city": data.get("city") or False,
            "district": data.get("district") or False,
            "country_code": data.get("country_code_raw") or False,
            "company_size": data.get("company_size") or False,
        }
        snapshot = Snapshot.search([("partner_id", "=", self.id)], limit=1)
        if snapshot:
            snapshot.write(values)
        else:
            Snapshot.create(dict(values, partner_id=self.id))

    @staticmethod
    def _iberinform_field_is_empty(value):
        """Não confundir os valores 0 ou relações existentes com ausência de dados."""
        return value is False or value is None or (isinstance(value, str) and not value.strip())

    def _iberinform_fill_empty_contact_values(self, data):
        """Preencher apenas campos em branco, inclusive no campo de dimensão.

        Os campos geográficos do módulo NUTS não são alterados. O distrito do
        Odoo só é atribuído quando corresponde ao país efetivo do contacto.
        """
        self.ensure_one()
        values = {}
        for contact_field in ("name", "street", "zip", "city"):
            value = data.get(contact_field)
            if value and self._iberinform_field_is_empty(self[contact_field]):
                values[contact_field] = value

        original_size = self._iberinform_normalize_company_size(data.get("company_size"))
        if original_size and self._iberinform_field_is_empty(self.iberinform_company_size):
            values["iberinform_company_size"] = original_size

        country = False
        if data.get("country_code"):
            country = self.env["res.country"].search([
                ("code", "=", data["country_code"]),
            ], limit=1)
            if country and not self.country_id:
                values["country_id"] = country.id

        effective_country_id = self.country_id.id or values.get("country_id")
        if data.get("district") and not self.state_id:
            state_domain = [("name", "=ilike", data["district"])]
            # Não associar um distrito português a uma morada cujo país já
            # foi escolhido manualmente e é diferente de Portugal.
            if country and effective_country_id == country.id:
                state_domain.append(("country_id", "=", country.id))
                state = self.env["res.country.state"].search(state_domain, limit=1)
                if state:
                    values["state_id"] = state.id

        return values

    # SICAE
    sicae_url = fields.Char(string="URL SICAE", readonly=True, copy=False)
    sicae_last_sync = fields.Datetime(string="Última atualização SICAE", readonly=True, copy=False)
    sicae_cae_primary = fields.Char(string="CAE principal (SICAE)", readonly=True, copy=False)
    sicae_cae_secondary = fields.Text(string="CAEs secundários (SICAE)", readonly=True, copy=False)
    sicae_cae_all = fields.Text(string="Todos os CAE (SICAE)", readonly=True, copy=False)

    _IBERINFORM_BASE_URL = "https://www.iberinform.pt"
    _SICAE_BASE_URL = "http://www.sicae.pt"
    _REQUEST_TIMEOUT = 20
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def action_get_iberinform_data(self):
        """Atualiza Iberinform e SICAE de forma independente em cada clique."""
        self.ensure_one()

        if not self.is_company:
            raise UserError(_("Esta funcionalidade está disponível apenas para contactos do tipo Empresa."))

        nif = self._normalize_nif(self.vat)
        if not nif:
            raise UserError(_("O contacto não tem um NIF/NIPC válido com 9 dígitos."))

        values = {}
        status = {}
        public_company_data = None

        # Cada clique faz sempre novas consultas. Uma fonte indisponível não
        # impede que a outra seja consultada e gravada.
        with requests.Session() as session:
            session.headers.update(self._HEADERS)

            # Iberinform
            try:
                company_url = self._iberinform_find_company_url(session, nif)
                company_data = self._iberinform_fetch_company_data(session, company_url, nif)
                values.update(self._iberinform_prepare_partner_values(company_data))
                values.update(self._iberinform_fill_empty_contact_values(company_data))
                public_company_data = company_data
                status["Iberinform"] = "OK"
            except (requests.RequestException, UserError, ValidationError) as exc:
                # Um 403 (acesso negado) ou 429 (pedidos em excesso) numa
                # atualização em massa NÃO deve originar novas consultas.
                # A fila suspende-se até um utilizador confirmar autorização.
                response = getattr(exc, "response", None)
                if (
                    self.env.context.get("iberinform_bulk_stop_on_denial")
                    and isinstance(exc, requests.HTTPError)
                    and response is not None
                    and response.status_code in (403, 429)
                ):
                    raise
                _logger.warning("Falha ao atualizar dados públicos para o NIF %s: %s", nif, exc, exc_info=True)
                status["Iberinform"] = self._public_source_error_message(exc)

            # SICAE
            try:
                sicae_data = self._sicae_fetch_cae_data(session, nif)
                values.update(self._sicae_prepare_partner_values(sicae_data))
                status["SICAE"] = "OK"
            except (requests.RequestException, UserError, ValidationError) as exc:
                response = getattr(exc, "response", None)
                if (
                    self.env.context.get("iberinform_bulk_stop_on_denial")
                    and isinstance(exc, requests.HTTPError)
                    and response is not None
                    and response.status_code in (403, 429)
                ):
                    raise
                _logger.warning("Falha ao atualizar SICAE para o NIF %s: %s", nif, exc, exc_info=True)
                status["SICAE"] = self._public_source_error_message(exc)

        successful_sources = [source for source, result in status.items() if result == "OK"]

        if not successful_sources:
            raise UserError(
                _(
                    "Não foi possível atualizar nenhuma das fontes.\n\n"
                    "Iberinform: %(iberinform)s\n"
                    "SICAE: %(sicae)s"
                )
                % {
                    "iberinform": status.get("Iberinform", _("Erro desconhecido")),
                    "sicae": status.get("SICAE", _("Erro desconhecido")),
                }
            )

        # Mantém os dados originais da fonte numa ficha própria; o contacto
        # recebe apenas campos que estavam vazios antes da consulta.
        if public_company_data is not None:
            self._iberinform_update_source_snapshot(public_company_data)
        self.write(values)

        both_ok = len(successful_sources) == 2
        message = _(
            "Iberinform: %(iberinform)s\nSICAE: %(sicae)s"
        ) % {
            "iberinform": status.get("Iberinform", _("Erro desconhecido")),
            "sicae": status.get("SICAE", _("Erro desconhecido")),
        }

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Dados públicos da empresa atualizados") if both_ok else _("Atualização parcial"),
                "message": message,
                "type": "success" if both_ok else "warning",
                "sticky": not both_ok,
                # A escrita é feita no servidor antes desta ação. O formulário
                # que está aberto no browser mantém, no entanto, os valores
                # antigos em cache. Depois de fechar a notificação, forçamos
                # o reload para mostrar imediatamente os campos SICAE gravados.
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def action_open_iberinform_bulk_update(self):
        """Abre o assistente de atualização de todas as empresas elegíveis."""
        return {
            "type": "ir.actions.act_window",
            "name": _("Atualizar dados de empresas"),
            "res_model": "iberinform.bulk.update.wizard",
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def _normalize_nif(self, vat):
        nif = re.sub(r"\D", "", vat or "")
        if len(nif) != 9:
            return False
        return nif

    # -------------------------------------------------------------------------
    # Iberinform
    # -------------------------------------------------------------------------

    def _iberinform_find_company_url(self, session, nif):
        response = session.get(
            urljoin(self._IBERINFORM_BASE_URL, "/resultados"),
            params={"criterioBusqueda": nif},
            timeout=self._REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        tree = html.fromstring(response.content)
        links = tree.xpath(
            '//section[@id="resultsSearchIber"]//tbody//a[starts-with(@href, "/empresa/")]/@href'
        )

        if not links:
            raise UserError(_("A Iberinform não devolveu nenhuma empresa para o NIF %s.") % nif)

        return urljoin(self._IBERINFORM_BASE_URL, links[0])

    def _iberinform_fetch_company_data(self, session, company_url, searched_nif):
        response = session.get(company_url, timeout=self._REQUEST_TIMEOUT)
        response.raise_for_status()
        tree = html.fromstring(response.content)

        structured = self._iberinform_parse_json_ld(tree)
        general = self._iberinform_parse_general_data(tree)
        cards = self._iberinform_parse_cards(tree)

        returned_nif = self._clean_text(
            structured.get("taxID") or self._xpath_text(tree, '//h2[contains(@class, "nif")]')
        )
        returned_nif = re.sub(r"\D", "", returned_nif or "")

        if returned_nif != searched_nif:
            raise ValidationError(
                _("A empresa devolvida pela Iberinform não corresponde ao NIF pesquisado (%s).")
                % searched_nif
            )

        address = structured.get("address") if isinstance(structured.get("address"), dict) else {}
        cae_raw = general.get("CAE") or ""
        cae_code, cae_description = self._iberinform_split_cae(cae_raw)
        postal_code = self._iberinform_extract_zip(address.get("postalCode") or general.get("Código postal"))
        city = self._clean_text(address.get("addressLocality") or general.get("Concelho"))
        street = self._iberinform_clean_street(
            address.get("streetAddress") or general.get("Morada"),
            postal_code,
            city,
        )

        return {
            "name": self._clean_text(structured.get("name") or general.get("Razão Social")),
            "raw_address": self._clean_text(general.get("Morada") or address.get("streetAddress")),
            "vat": returned_nif,
            "street": street,
            "zip": postal_code,
            "city": city,
            "district": self._clean_text(address.get("addressRegion") or general.get("Distrito")),
            "country_code": self._clean_text(address.get("addressCountry")) or "PT",
            "country_code_raw": self._clean_text(address.get("addressCountry")),
            "legal_form": general.get("Forma jurídica"),
            "municipality": general.get("Concelho"),
            "cae_code": cae_code,
            "cae_description": cae_description,
            "sector": general.get("Setor da empresa"),
            "constitution_date": self._iberinform_parse_date(general.get("Data de constituição")),
            "turnover": cards.get("Volume de negócios"),
            "share_capital": cards.get("Capital social"),
            "turnover_evolution": cards.get("Evolução volume de negócios"),
            "company_size": cards.get("Dimensão da empresa"),
            "employees": cards.get("Empregados"),
            "source_url": company_url,
        }

    def _iberinform_parse_json_ld(self, tree):
        for raw in tree.xpath('//script[@type="application/ld+json"]/text()'):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict):
                entity = data.get("mainEntity")
                if isinstance(entity, dict) and entity.get("@type") == "Organization":
                    return entity
        return {}

    def _iberinform_parse_general_data(self, tree):
        data = {}
        for item in tree.xpath('//div[@id="detalleEmpresa"]//ul[contains(@class, "company-data")]/li'):
            title_nodes = item.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " title ")]')
            info_nodes = item.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " info ")]')
            if not title_nodes or not info_nodes:
                continue

            key = self._clean_text(title_nodes[0].text_content())
            value = self._clean_text(info_nodes[0].text_content())
            if not key or not value:
                continue

            if key.startswith("NIF/NIPC de "):
                key = "NIF/NIPC"
            elif key.startswith("Morada de "):
                key = "Morada"

            data[key] = value
        return data

    def _iberinform_parse_cards(self, tree):
        data = {}
        for xpath_expr in (
            '//div[contains(@class, "datos-text")]',
            '//div[contains(@class, "card-facturacion")]',
        ):
            for block in tree.xpath(xpath_expr):
                title = block.xpath('.//h3[1]')
                value = block.xpath('.//p[1]')
                if not title or not value:
                    continue
                key = self._clean_text(title[0].text_content())
                val = self._clean_text(value[0].text_content())
                if key and val:
                    data[key] = val
        return data

    def _iberinform_prepare_partner_values(self, data):
        """Atualiza apenas informação da própria fonte, não a ficha do contacto.

        Os campos readonly da Iberinform mostram os dados oficiais mais recentes.
        O campo editável iberinform_company_size fica de fora, para preservar
        correções manuais; a dimensão original é guardada no snapshot público.
        """
        return {
            "iberinform_url": data.get("source_url") or False,
            "iberinform_last_sync": fields.Datetime.now(),
            "iberinform_legal_form": data.get("legal_form") or False,
            "iberinform_municipality": data.get("municipality") or False,
            "iberinform_cae_code": data.get("cae_code") or False,
            "iberinform_cae_description": data.get("cae_description") or False,
            "iberinform_sector": data.get("sector") or False,
            "iberinform_constitution_date": data.get("constitution_date") or False,
            "iberinform_turnover": data.get("turnover") or False,
            "iberinform_share_capital": data.get("share_capital") or False,
            "iberinform_turnover_evolution": data.get("turnover_evolution") or False,
            "iberinform_employees": data.get("employees") or False,
        }

    # -------------------------------------------------------------------------
    # SICAE
    # -------------------------------------------------------------------------

    def _sicae_fetch_cae_data(self, session, nif):
        """Consulta a ficha pública SICAE diretamente pelo NIPC e extrai todos os CAE."""
        source_url = urljoin(self._SICAE_BASE_URL, "/Detalhe.aspx")

        # O SICAE funciona em HTTP e, na prática, responde de forma mais fiável
        # quando o pedido se aproxima do Microsoft Edge. Não usamos HTTPS aqui.
        edge_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        # Abre primeiro a página de consulta para obter eventuais cookies de
        # sessão ASP.NET usados pelo site, mas uma falha aqui não impede a
        # tentativa direta à ficha da empresa.
        try:
            session.get(
                urljoin(self._SICAE_BASE_URL, "/Consulta.aspx"),
                timeout=self._REQUEST_TIMEOUT,
                allow_redirects=False,
                headers=edge_headers,
            )
        except requests.RequestException:
            pass

        headers = dict(edge_headers)
        headers["Referer"] = urljoin(self._SICAE_BASE_URL, "/Consulta.aspx")

        response = session.get(
            source_url,
            params={"NIPC": nif},
            timeout=self._REQUEST_TIMEOUT,
            allow_redirects=False,
            headers=headers,
        )
        if 300 <= response.status_code < 400:
            raise UserError(
                _(
                    "O SICAE tentou redirecionar a consulta HTTP para outro endereço "
                    "(%s). A consulta foi interrompida para não usar HTTPS."
                ) % response.headers.get("Location", "sem destino indicado")
            )
        response.raise_for_status()

        # O site é antigo e nem sempre declara corretamente o encoding.
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"

        tree = html.fromstring(response.text)

        def _norm(value):
            value = value or ""
            value = value.replace("\xa0", " ").replace("\u200b", " ")
            return re.sub(r"\s+", " ", value).strip()

        # 1) Preferir linhas-folha da tabela. O HTML do SICAE usa tabelas
        #    aninhadas e um <tr> exterior pode conter, ao mesmo tempo, o CAE
        #    principal e vários CAE secundários. Se esse <tr> for tratado como
        #    uma linha real, o último código pode ser associado ao rótulo
        #    errado e ficar indevidamente marcado como já processado.
        primary = False
        secondaries = []
        seen_codes = set()

        for row in tree.xpath("//tr[not(.//tr)]"):
            row_text = _norm(" ".join(row.xpath(".//text()")))
            if not row_text:
                continue

            codes = re.findall(r"(?<!\d)(\d{5})(?!\d)", row_text)
            if not codes:
                continue

            if re.search(r"\bCAE\s*PRINCIPAL\b", row_text, flags=re.IGNORECASE):
                # Numa linha-folha do SICAE o código associado ao rótulo é o
                # último código de 5 dígitos da própria linha. Não substituímos
                # um principal já encontrado por duplicados de apresentação.
                if not primary:
                    primary = codes[-1]
                    seen_codes.add(primary)
                continue

            sec_match = re.search(
                r"\bCAE\s*SECUND[AÁ]RIO(?:\s*(\d+))?\b",
                row_text,
                flags=re.IGNORECASE,
            )
            if sec_match:
                code = codes[-1]
                if code in seen_codes:
                    continue
                position = sec_match.group(1)
                secondaries.append({
                    "position": int(position) if position and position.isdigit() else len(secondaries) + 1,
                    "code": code,
                })
                seen_codes.add(code)

        # 2) Complementar sempre com uma leitura por texto corrido. Isto não é
        #    apenas um fallback para o caso de zero secundários: se a leitura
        #    por linhas encontrar apenas parte dos CAE, os restantes são
        #    acrescentados aqui sem duplicar códigos já encontrados.
        page_text = _norm(tree.text_content())

        if not primary:
            principal_match = re.search(
                r"\bCAE\s*PRINCIPAL\b.{0,80}?(?<!\d)(\d{5})(?!\d)",
                page_text,
                flags=re.IGNORECASE,
            )
            if principal_match:
                primary = principal_match.group(1)
                seen_codes.add(primary)

        if primary:
            for match in re.finditer(
                r"\bCAE\s*SECUND[AÁ]RIO(?:\s*(\d+))?\b.{0,80}?(?<!\d)(\d{5})(?!\d)",
                page_text,
                flags=re.IGNORECASE,
            ):
                position, code = match.groups()
                if code == primary or code in seen_codes:
                    continue
                secondaries.append({
                    "position": int(position) if position and position.isdigit() else len(secondaries) + 1,
                    "code": code,
                })
                seen_codes.add(code)

        if not primary:
            # Não expomos o HTML completo ao utilizador, mas deixamos no log uma
            # amostra suficiente para diagnosticar alterações futuras do SICAE.
            _logger.warning(
                "SICAE sem CAE principal para NIF %s. HTTP %s. URL %s. Conteúdo: %s",
                nif,
                response.status_code,
                response.url,
                page_text[:1000],
            )
            raise UserError(
                _(
                    "O SICAE respondeu à consulta do NIF %s, mas o módulo não encontrou "
                    "o CAE principal na página devolvida. Consulte o log do Odoo para ver "
                    "o conteúdo recebido do SICAE."
                ) % nif
            )

        secondaries.sort(key=lambda item: item["position"])

        return {
            "source_url": response.url,
            "primary": primary,
            "secondaries": secondaries,
        }

    def _sicae_prepare_partner_values(self, data):
        primary = data.get("primary")
        secondaries = data.get("secondaries") or []

        secondary_text = "\n".join(
            _("CAE Secundário %(position)s: %(code)s")
            % {"position": item["position"], "code": item["code"]}
            for item in secondaries
        )

        all_lines = []
        if primary:
            all_lines.append(_("CAE Principal: %s") % primary)
        if secondary_text:
            all_lines.append(secondary_text)

        return {
            "sicae_url": data.get("source_url"),
            "sicae_last_sync": fields.Datetime.now(),
            "sicae_cae_primary": primary or False,
            "sicae_cae_secondary": secondary_text or False,
            "sicae_cae_all": "\n".join(all_lines) or False,
        }

    @staticmethod
    def _public_source_error_message(exc):
        """Mensagem curta para a notificação sem expor demasiado detalhe técnico."""
        if isinstance(exc, requests.Timeout):
            return _("Indisponível (timeout)")
        if isinstance(exc, requests.ConnectionError):
            return _("Indisponível (ligação)")
        if isinstance(exc, requests.HTTPError):
            response = getattr(exc, "response", None)
            if response is not None:
                return _("Erro HTTP %s") % response.status_code
            return _("Erro HTTP")
        message = str(exc).strip()
        return message or _("Erro na consulta")

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _clean_text(value):
        if value is None:
            return False
        return re.sub(r"\s+", " ", str(value)).strip() or False

    @staticmethod
    def _xpath_text(tree, xpath_expr):
        nodes = tree.xpath(xpath_expr)
        if not nodes:
            return False
        node = nodes[0]
        text = node.text_content() if hasattr(node, "text_content") else str(node)
        return re.sub(r"\s+", " ", text).strip() or False

    @staticmethod
    def _iberinform_split_cae(value):
        value = (value or "").strip()
        match = re.match(r"^(\d+)\s*-\s*(.+)$", value)
        if match:
            return match.group(1), match.group(2).strip()
        if value.isdigit():
            return value, False
        return False, value or False

    @staticmethod
    def _iberinform_extract_zip(value):
        if not value:
            return False
        match = re.search(r"\b\d{4}-\d{3}\b", value)
        return match.group(0) if match else False

    @staticmethod
    def _iberinform_clean_street(value, zip_code=False, city=False):
        if not value:
            return False
        result = re.sub(r"\s+", " ", value).strip()
        if zip_code:
            result = re.sub(rf"\s*{re.escape(zip_code)}\s*-?\s*", " ", result, flags=re.IGNORECASE)
        if city:
            result = re.sub(rf"\b{re.escape(city)}\b\.?(?=\s|$)", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\bPORTUGAL\.?\s*$", "", result, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", result).strip(" ,.-") or False

    @staticmethod
    def _iberinform_normalize_company_size(value):
        """Converte a dimensão devolvida pela fonte para um dos valores do dropdown."""
        if not value:
            return False

        raw = re.sub(r"\s+", " ", str(value)).strip()
        normalized = unicodedata.normalize("NFKD", raw)
        normalized = "".join(char for char in normalized if not unicodedata.combining(char)).lower()

        # Aceita variantes como "Microempresa", "Pequena empresa",
        # "Média empresa" ou texto adicional devolvido pela fonte.
        if "micro" in normalized:
            return "Micro"
        if "pequen" in normalized:
            return "Pequena"
        if "media" in normalized:
            return "Média"
        if "grande" in normalized:
            return "Grande"
        return False

    @staticmethod
    def _iberinform_parse_date(value):
        if not value:
            return False
        value = value.strip()
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return False
