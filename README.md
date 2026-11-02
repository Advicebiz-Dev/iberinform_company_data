# Iberinform + SICAE — Dados da Empresa

Módulo personalizado para Odoo 19.

## Funcionalidades

- Obtém automaticamente dados públicos de empresas através da Iberinform e do SICAE, utilizando o NIF/NIPC.
- Consulta informações como nome, morada, distrito, concelho, forma jurídica, CAE, setor, dimensão, trabalhadores e indicadores públicos.
- Identifica o CAE principal e os CAE secundários.
- Mantém os dados de cada fonte separados na aba **Dados públicos**.
- Preserva os dados introduzidos manualmente no contacto, preenchendo apenas campos vazios.
- Guarda os dados originais da Iberinform para consulta, mesmo quando diferem dos dados do contacto.
- Permite atualizar individualmente ou em massa os dados das empresas.

## Atualização em lotes

- Permite atualizar várias empresas através de uma fila automática.
- Processa, por defeito, **1 empresa a cada 15 minutos**, com opções de 2 ou 3 por lote.
- Apresenta o progresso e o estado de cada atualização.
- Permite iniciar manualmente lotes disponíveis.
- Suspende automaticamente as consultas em caso de bloqueio HTTP 403/429.
- Permite retomar o processamento após confirmação das condições de acesso.
- Apresenta os horários de processamento no fuso horário do utilizador.

## Pesquisa por CAE

Permite pesquisar empresas através de:

- **CAE principal ou secundário:** pesquisa em todos os CAE disponíveis.
- **Só CAE principal:** pesquisa nos CAE principais da Iberinform ou SICAE.
- **Só CAE secundário:** pesquisa nos CAE secundários do SICAE.
- **Com CAE secundário:** filtra empresas com CAE secundários registados.
- **Sem dados SICAE:** identifica empresas sem informação SICAE.

Aceita códigos completos ou parciais.

## Versão 19.0.1.9.1

- Adiciona filtros de pesquisa por CAE principal e secundário.
- Corrige a apresentação dos horários dos lotes.
- Mantém o processamento automático com intervalos mínimos de 15 minutos.
- Preserva os dados preenchidos manualmente.
- Mantém o histórico dos dados públicos originais.
- Melhora a leitura e identificação dos CAE secundários do SICAE.

## Atualização

1. Efetuar backup da base de dados.
2. Substituir a pasta `iberinform_company_data`.
3. Reiniciar o Odoo.
4. Atualizar o módulo.
5. Confirmar que a ação agendada **Iberinform — processar um lote autorizado** está ativa.
6. Atualizar o navegador (`Ctrl + F5`).
7. Testar a consulta individual, os filtros CAE e a atualização em lotes.

**Nota:** As consultas dependem da disponibilidade e das permissões de acesso da Iberinform e do SICAE. O módulo não contorna bloqueios ou restrições impostos pelas fontes.
