{
    "name": "Iberinform + SICAE - Dados da Empresa",
    "version": "19.0.1.9.1",
    "category": "Contacts",
    "summary": "Consulta Iberinform e SICAE em lotes, preservando dados manuais",
    "author": "Advicebiz",
    "license": "LGPL-3",
    "depends": ["contacts"],
    "data": [
        "security/ir.model.access.csv",
        "views/bulk_job_views.xml",
        "views/res_partner_views.xml",
        "data/cron.xml",
        "views/bulk_update_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
