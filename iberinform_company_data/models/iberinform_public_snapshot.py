# -*- coding: utf-8 -*-
from odoo import fields, models


class IberinformPublicSnapshot(models.Model):
    _name = "iberinform.public.snapshot"
    _description = "Última informação pública original da Iberinform"
    _rec_name = "name"

    partner_id = fields.Many2one(
        "res.partner", string="Contacto", required=True,
        index=True, ondelete="cascade", readonly=True, copy=False,
    )
    name = fields.Char(string="Nome público", readonly=True, copy=False)
    vat = fields.Char(string="NIF/NIPC público", readonly=True, copy=False)
    address = fields.Char(string="Morada original", readonly=True, copy=False)
    street = fields.Char(string="Rua", readonly=True, copy=False)
    zip = fields.Char(string="Código postal", readonly=True, copy=False)
    city = fields.Char(string="Localidade", readonly=True, copy=False)
    district = fields.Char(string="Distrito", readonly=True, copy=False)
    country_code = fields.Char(string="País (código)", readonly=True, copy=False)
    company_size = fields.Char(string="Dimensão original", readonly=True, copy=False)

    _partner_unique = models.Constraint(
        "UNIQUE(partner_id)",
        "Já existem dados públicos Iberinform para este contacto.",
    )
