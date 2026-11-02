# Iberinform + SICAE - Dados da Empresa (Odoo 19)

Extensão de `res.partner` para contactos do tipo **Empresa**.

Quando existe NIF/NIPC, mostra o botão **Obter dados Iberinform + SICAE**.

## Iberinform

Consulta a pesquisa pública por NIF, abre a ficha da empresa e obtém os dados públicos disponíveis, incluindo morada, concelho, distrito, forma jurídica, CAE principal, setor, data de constituição, dimensão, empregados e indicadores públicos.

## SICAE

Consulta diretamente:

`https://www.sicae.pt/Detalhe.aspx?NIPC=<NIF>`

Extrai o **CAE Principal** e todos os **CAE Secundários** publicados pelo SICAE.

Os CAE do SICAE são guardados separadamente dos dados Iberinform para ser sempre clara a origem de cada informação.

## Instalação

1. Copiar a pasta `iberinform_company_data` para `custom_addons`.
2. Reiniciar o Odoo.
3. Atualizar a lista de aplicações.
4. Instalar ou atualizar o módulo **Iberinform + SICAE - Dados da Empresa**.

Se já tiver a versão anterior instalada, basta substituir a pasta pela nova versão e executar **Atualizar** no módulo.


## v1.2 — atualização independente das fontes

- Cada clique no botão faz uma nova consulta à Iberinform e ao SICAE.
- Se a Iberinform falhar, os dados do SICAE são atualizados na mesma.
- Se o SICAE falhar, os dados da Iberinform são atualizados na mesma.
- Se ambas as fontes falharem, nenhuma alteração é gravada e é apresentado um erro.
- Quando uma fonte responde com sucesso, os respetivos campos próprios são regravados para evitar manter dados antigos.


## v1.5.2 — dimensão da empresa em dropdown

- O campo **Dimensão da empresa** passou a ser uma seleção com os valores **Micro**, **Pequena**, **Média** e **Grande**.
- A atualização automática continua a preencher o campo e normaliza a designação recebida pela Iberinform para uma destas quatro opções.
- O campo pode ser ajustado manualmente no contacto; uma nova sincronização volta a aplicar o valor obtido automaticamente.


## v1.5.3 — merge: dropdown de dimensão + correção dos CAE secundários SICAE

- Mantém o campo **Dimensão da empresa** como seleção com os valores **Micro**, **Pequena**, **Média** e **Grande**.
- Mantém a normalização automática da dimensão recebida da Iberinform e a possibilidade de ajuste manual.
- Corrige a leitura de tabelas HTML aninhadas do SICAE, evitando que uma linha exterior agregue vários CAE e faça um código secundário ser descartado.
- A leitura por texto corrido passa a complementar os CAE já encontrados, mesmo quando já foi detetado pelo menos um CAE secundário.
- Mantém a deduplicação dos códigos e a ordenação pela posição apresentada pelo SICAE.


## v1.6.0 — preservar dados escritos manualmente e guardar valores públicos originais

- A atualização nunca substitui **Nome, Rua, Código postal, Localidade, País ou Distrito** já preenchidos na ficha do contacto. Só preenche os que estiverem vazios no momento da consulta.
- O campo editável **Dimensão da empresa** também só recebe a dimensão normalizada da Iberinform quando estiver vazio; uma correção manual é preservada.
- Em **Contactos → Dados públicos → Iberinform**, apresenta agora a identificação e a morada originais obtidas na última consulta com sucesso: nome, NIF, morada original, rua limpa, código postal, localidade, distrito, país e dimensão original (não normalizada). Estes valores são independentes dos dados do contacto.
- Os dados originais são guardados no novo modelo `iberinform.public.snapshot`, com um registo por contacto. Os campos que os apresentam na ficha do contacto são calculados e **não acrescentam colunas à tabela `res_partner`**.
- Os dados específicos das fontes que já eram só de consulta (CAE, setor, forma jurídica, indicadores, SICAE etc.) continuam a refletir a última resposta de cada fonte e são atualizados normalmente.
- Os campos do módulo NUTS não são alterados. A atualização individual e em massa usam a mesma regra de preenchimento de campos vazios.
- As fichas com consultas anteriores mostrarão o novo bloco original após **a próxima consulta** à Iberinform; os dados anteriormente preenchidos nos contactos não são alterados durante a atualização do módulo.
- Instalação de atualização: **substituir a pasta, parar o Odoo, atualizar o módulo (`-u iberinform_company_data --stop-after-init`), reiniciar o servidor**. Recomendado testar em DEV e fazer backup antes de PRE/PROD.

## v19.0.1.7.0 — Atualização em lotes, com paragem em 403/429

A funcionalidade «Atualizar dados públicos das empresas» passou a **criar
uma fila persistente**. A interface não fica à espera de todas as consultas.

- Por defeito são processadas **1 empresa de cada vez**, **nunca antes de 15
  minutos** desde o lote anterior. Existem opções de 2 ou 3 empresas por lote,
  mas a opção 1 é a mais conservadora.
- O Odoo cria a ação agendada «Iberinform — processar um lote autorizado»
  (periodicidade: 15 minutos). É necessário que o serviço de tarefas agendadas
  do servidor esteja ativo (`max_cron_threads` não pode ser zero).
- Ao criar a fila, a ação agendada é solicitada para arrancar assim que um
  worker estiver disponível. A hora exata depende da configuração do servidor.
- O estado fica disponível no botão «Histórico de atualizações em lotes» na
  lista de Contactos/Empresas. Pode atualizar a página ou usar «Atualizar estado».
- «Processar lote disponível» permite iniciar manualmente um lote que já esteja
  elegível, sem contornar o período de espera de 15 minutos.
- Cada empresa é marcada como Completa, Parcial ou Falha; as bem-sucedidas não
  são repetidas. Um erro 403/429 da Iberinform **ou** SICAE marca a empresa como
  Bloqueada, coloca a fila em Pausa e impede novas consultas automáticas.
- Para retomar uma fila bloqueada, primeiro confirmar a autorização/limites de
  acesso com o fornecedor; só depois usar «Retomar após confirmar acesso».
- Nunca recorre a proxies, mudança de IP, rotação de identidade, tentativas
  automáticas após bloqueio nem outras técnicas para contornar restrições.
- As regras da versão 1.6 permanecem: contactos já preenchidos preservados;
  valores públicos originais guardados na aba «Dados públicos»; SICAE
  independente quando a consulta individual é utilizada.

### IMPORTANTE sobre HTTP 403

403 é uma recusa de acesso e **não prova** que a causa seja somente o número de
consultas. Se o 403 persistir com uma única empresa por lote, é necessário
solicitar à Iberinform uma API/serviço autorizado ou esclarecer quotas e
whitelists. O módulo não tenta ultrapassar um bloqueio explícito.

### Instalação

1. Criar backup em DEV.
2. Substituir a pasta `iberinform_company_data` pela desta versão, sem
   desinstalar o módulo existente.
3. Reiniciar o Odoo e fazer **Upgrade** do módulo em Aplicações.
4. Confirmar que a ação agendada está ativa em Definições > Técnico > Automação
   > Ações agendadas (o nome pode variar com o idioma).
5. Testar primeiro com 2 ou 3 empresas e lote de 1, sem sobrecarregar o site.

A versão foi testada isoladamente (lógica Python e XML), não num servidor Odoo
19 funcional. Não garante que o fornecedor aceite as consultas, mesmo lentas.


## Correção 19.0.1.8.0 — horários dos lotes

- Os horários na vista são convertidos automaticamente pelo Odoo para o fuso
  das Preferências do utilizador. O campo Datetime interno mantém-se em UTC.
- Ao clicar **Processar lote disponível** antes do prazo, é mostrada uma
  notificação com o horário convertido para o fuso do utilizador, em vez de
  um erro com o timestamp UTC. A ficha é reaberta automaticamente para
  atualizar o próximo horário e as contagens, entretanto alterados pela cron.
- O agendamento de 15 minutos, a limitação do lote e as paragens por 403/429
  não foram alterados. Não há campos de base de dados novos nesta versão.

Se o fuso das Preferências do utilizador estiver mal configurado, o Odoo
mostrará o horário desse fuso. Confirme as Preferências do utilizador.

## Pesquisa por CAE (19.0.1.9.1)

Na pesquisa de Contactos passam a existir as opções:

- **CAE (principal ou secundário)** — devolve as empresas em que o código é o CAE principal (SICAE ou Iberinform) **ou** um dos CAE secundários do SICAE. É a opção por omissão.
- **Só CAE principal** — SICAE ou Iberinform.
- **Só CAE secundário** — só nos CAE secundários do SICAE.

Aceita o código completo (`46900`) ou o início (`469`) para apanhar uma subclasse/grupo.
Filtros adicionais: **Com CAE secundário** e **Sem dados SICAE**.
