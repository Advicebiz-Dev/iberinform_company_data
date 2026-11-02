# Testes DEV — Iberinform + SICAE 19.0.1.8.0

1. Backup da base de dados e upgrade do módulo (sem desinstalar).
2. Confirmar acesso normal a Contactos e funcionamento da consulta individual.
3. Preencher manualmente Rua e Código postal; consultar dados públicos e
   confirmar que o Odoo conserva os valores, mostrando os originais na aba
   «Dados públicos».
4. Abrir a lista de Contactos, clicar «Atualizar dados públicos das empresas»,
   desselecionar as restantes e selecionar duas empresas de teste.
5. Configurar **1 empresa por lote**; criar fila. Deve abrir o formulário
   de acompanhamento sem tentar consultar as duas empresas na mesma chamada HTTP.
6. Confirmar que apenas uma empresa é processada no primeiro lote e que o
   campo «Próximo lote a partir de» aponta para pelo menos 15 minutos depois.
7. Clicar «Processar lote disponível» antes do prazo: deve bloquear o pedido,
   sem executar consulta ao fornecedor.
8. Depois do prazo, confirmar que a cron trata a próxima empresa e que a fila
   fica «Concluído»; resultados e falhas devem ser visíveis por empresa.
9. Num ambiente de testes, simular uma resposta HTTP 403 da Iberinform na
   primeira consulta da fila: confirmar **Pausado por bloqueio do fornecedor**,
   empresa «Bloqueada», e nenhuma consulta seguinte feita.
10. Simular HTTP 429 do SICAE: mesmo comportamento de pausa.
11. Confirmar que a cron NÃO retoma automaticamente uma fila pausada. A retoma
    deve exigir ação humana após verificar autorização para prosseguir.
12. Cancelar uma fila e confirmar que não processa mais empresas.
13. Verificar que duas filas não são criadas em paralelo pelo assistente.
14. Confirmar integridade de dados do módulo NUTS e dos contactos existentes.

**Nota:** resultados dos testes isolados não constituem prova de instalação
real no Odoo 19 nem de autorização do fornecedor.

## Testes adicionais v1.8 — fusos horários e atualização

15. Com o utilizador em Europe/Lisbon, confirmar que, a 15/10/2026, o
    horário na notificação está em hora de verão WEST (UTC+1) e corresponde
    ao campo «Próximo lote a partir de».
16. Clicar «Processar lote disponível» antes do prazo: deve aparecer aviso,
    sem RPC_ERROR nem nova consulta, e a ficha deve recarregar-se.
17. Confirmar que «Atualizar estado» relê os resultados após lote automático.
18. Conferir uma data de inverno: Europe/Lisbon = WET (UTC+0).
