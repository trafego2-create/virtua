-- Virtua — sistema de cobranças (substitui o Virtua Software)
-- Tudo no schema "virtua". Rodar uma vez no SQL Editor do Supabase (ou via scripts/aplicar_schema.py).
-- Pode ser rodado de novo: só cria o que não existe e recria views/funções.

create schema if not exists virtua;

-- ---------- usuários do sistema (login próprio, não usa o Auth do Supabase) ----------
create table if not exists virtua.usuarios (
  id           bigserial primary key,
  nome         text        not null,
  email        text        not null unique check (email = lower(email)),
  perfil       text        not null check (perfil in ('administrador', 'gestor', 'financeiro', 'consulta')),
  senha_hash   text,
  ativo        boolean     not null default true,
  criado_em    timestamptz not null default now()
);

-- ---------- regras que a administradora ajusta pela tela de Configurações ----------
create table if not exists virtua.config (
  chave          text primary key,
  valor          text not null,
  descricao      text not null,
  atualizado_em  timestamptz not null default now()
);
insert into virtua.config (chave, valor, descricao) values
  ('corte_carteira_ativa', '2026-01-01', 'Cliente com acordo ou com vencimento a partir desta data entra na carteira ativa'),
  ('multa_pct',            '2',          'Multa por atraso (%)'),
  ('juros_mes_pct',        '1',          'Juros de mora ao mês (%), proporcional aos dias de atraso')
on conflict (chave) do nothing;

-- ---------- carteira ----------
create table if not exists virtua.clientes (
  codigo         text primary key,              -- "Cód. Cliente" do Virtua; clientes novos recebem N-<seq>
  cpf_cnpj       text not null,
  nome           text not null,
  telefone       text,
  email          text,
  uf             text,
  observacao     text,
  criado_em      timestamptz not null default now(),
  atualizado_em  timestamptz not null default now()
);
create index if not exists clientes_cpf on virtua.clientes (cpf_cnpj);

create table if not exists virtua.contratos (
  conta           text primary key,             -- "Conta" do Virtua = HP + transação Hotmart
  codigo_cliente  text not null references virtua.clientes (codigo),
  produto         text,
  lote            text,                         -- "Garantias Reais" do Virtua (lote de importação)
  origem          text not null default 'virtua',
  criado_em       timestamptz not null default now()
);
create index if not exists contratos_cliente on virtua.contratos (codigo_cliente);

create table if not exists virtua.acordos (
  nr_acordo                 text primary key,
  codigo_cliente            text not null references virtua.clientes (codigo),
  conta                     text references virtua.contratos (conta),
  data_acordo               date,
  valor_original            numeric(12, 2) not null default 0,
  valor_desconto            numeric(12, 2) not null default 0,
  valor_total               numeric(12, 2) not null default 0,
  qtde_parcelas             int,
  vencimentos_renegociados  text,               -- datas das mensalidades originais que o acordo substituiu
  criado_em                 timestamptz not null default now()
);
create index if not exists acordos_cliente on virtua.acordos (codigo_cliente);

create sequence if not exists virtua.clientes_novos_seq;
create sequence if not exists virtua.acordos_novos_seq start 10000;

-- situacao guarda o que alguém decidiu (paga, renegociada, cancelada).
-- "vencida" x "a vencer" não é guardado: sai da data, na view v_parcelas.
create table if not exists virtua.parcelas (
  id                   bigserial primary key,
  codigo_cliente       text not null references virtua.clientes (codigo),
  conta                text references virtua.contratos (conta),
  nr_acordo            text references virtua.acordos (nr_acordo),
  nr_parcela           int,
  vencimento           date not null,
  valor_previsto       numeric(12, 2) not null,
  pago_em              date,
  valor_pago           numeric(12, 2) not null default 0,
  nosso_numero         text,
  emissao_boleto       text,
  situacao             text not null check (situacao in ('aberta', 'paga', 'renegociada', 'cancelada')),
  retirar_da_cobranca  boolean not null default false,
  origem               text not null default 'virtua',
  linha_origem         int,                     -- linha no CSV do Virtua (rastreio da migração)
  criado_em            timestamptz not null default now(),
  atualizado_em        timestamptz not null default now(),
  check ((situacao = 'paga') = (pago_em is not null))
);
create index if not exists parcelas_cliente on virtua.parcelas (codigo_cliente);
create index if not exists parcelas_venc on virtua.parcelas (vencimento) where situacao = 'aberta';
create index if not exists parcelas_acordo on virtua.parcelas (nr_acordo);

-- ---------- histórico de alterações ----------
create table if not exists virtua.auditoria (
  id        bigserial primary key,
  em        timestamptz not null default now(),
  usuario   text not null,
  tabela    text not null,
  registro  text not null,
  acao      text not null,                      -- inseriu | alterou | excluiu | carga
  antes     jsonb,
  depois    jsonb
);
create index if not exists auditoria_registro on virtua.auditoria (tabela, registro);
create index if not exists auditoria_em on virtua.auditoria (em desc);

-- O app grava o usuário logado em virtua.usuario no início de cada transação.
-- A carga da migração liga virtua.sem_auditoria e registra uma linha só de "carga".
create or replace function virtua.registrar_auditoria() returns trigger
language plpgsql as $$
declare
  quem    text := coalesce(nullif(current_setting('virtua.usuario', true), ''), 'sistema');
  chave   text;
  velho   jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end;
  novo    jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end;
begin
  if current_setting('virtua.sem_auditoria', true) = 'on' then
    return coalesce(new, old);
  end if;
  if tg_table_name = 'usuarios' then
    velho := velho - 'senha_hash';
    novo  := novo - 'senha_hash';
    if tg_op = 'UPDATE' and velho = novo then   -- só trocou a senha
      velho := jsonb_build_object('senha', 'anterior');
      novo  := jsonb_build_object('senha', 'alterada');
    end if;
  end if;
  if tg_op = 'UPDATE' and velho = novo then
    return new;
  end if;
  chave := coalesce(novo, velho) ->> tg_argv[0];
  insert into virtua.auditoria (usuario, tabela, registro, acao, antes, depois)
  values (quem, tg_table_name, chave,
          case tg_op when 'INSERT' then 'inseriu' when 'UPDATE' then 'alterou' else 'excluiu' end,
          velho, novo);
  return coalesce(new, old);
end $$;

create or replace function virtua.tocar_atualizado_em() returns trigger
language plpgsql as $$
begin
  new.atualizado_em := now();
  return new;
end $$;

do $$
declare t record;
begin
  for t in select * from (values
      ('clientes', 'codigo'), ('contratos', 'conta'), ('acordos', 'nr_acordo'),
      ('parcelas', 'id'), ('usuarios', 'email'), ('config', 'chave')) as x(tabela, chave)
  loop
    execute format('drop trigger if exists auditoria on virtua.%I', t.tabela);
    execute format('create trigger auditoria after insert or update or delete on virtua.%I
                    for each row execute function virtua.registrar_auditoria(%L)', t.tabela, t.chave);
  end loop;
  foreach t.tabela in array array['clientes', 'parcelas', 'config'] loop
    execute format('drop trigger if exists tocar on virtua.%I', t.tabela);
    execute format('create trigger tocar before update on virtua.%I
                    for each row execute function virtua.tocar_atualizado_em()', t.tabela);
  end loop;
end $$;

-- "Hoje" no fuso de Brasília: o banco roda em UTC, e virtua.hoje() viraria o dia seguinte às 21h.
create or replace function virtua.hoje() returns date
language sql stable as $$ select (now() at time zone 'America/Sao_Paulo')::date $$;

-- ---------- leitura: status, atraso, valor atualizado e carteira ----------
create or replace view virtua.v_parcelas as
with cfg as (
  select max(valor) filter (where chave = 'multa_pct')::numeric     as multa_pct,
         max(valor) filter (where chave = 'juros_mes_pct')::numeric as juros_mes_pct
  from virtua.config
)
select p.*,
       case when p.situacao <> 'aberta' then p.situacao
            when p.vencimento < virtua.hoje() then 'vencida'
            else 'a_vencer' end                                                   as status,
       case when p.situacao = 'aberta' and p.vencimento < virtua.hoje()
            then virtua.hoje() - p.vencimento else 0 end                           as dias_atraso,
       case when p.situacao = 'aberta' and p.vencimento < virtua.hoje()
            then round(p.valor_previsto * (1 + cfg.multa_pct / 100
                       + cfg.juros_mes_pct / 100 * (virtua.hoje() - p.vencimento) / 30.0), 2)
            else p.valor_previsto end                                             as valor_atualizado
from virtua.parcelas p cross join cfg;

create or replace view virtua.v_clientes as
with corte as (
  select valor::date as data from virtua.config where chave = 'corte_carteira_ativa'
), tot as (
  select codigo_cliente,
         sum(valor_previsto) filter (where status <> 'renegociada' and status <> 'cancelada') as total_contratado,
         sum(valor_pago)                                                                     as total_recebido,
         sum(valor_previsto) filter (where status in ('vencida', 'a_vencer'))                as total_em_aberto,
         sum(valor_previsto) filter (where status = 'vencida')                               as total_vencido,
         count(*) filter (where status = 'vencida')                                          as parcelas_vencidas,
         max(dias_atraso)                                                                    as maior_atraso,
         max(pago_em)                                                                        as ultimo_pagamento,
         bool_or(nr_acordo is not null)                                                      as tem_acordo,
         max(vencimento)                                                                     as ultimo_vencimento
  from virtua.v_parcelas
  group by codigo_cliente
)
select c.*,
       coalesce(t.total_contratado, 0)  as total_contratado,
       coalesce(t.total_recebido, 0)    as total_recebido,
       coalesce(t.total_em_aberto, 0)   as total_em_aberto,
       coalesce(t.total_vencido, 0)     as total_vencido,
       coalesce(t.parcelas_vencidas, 0) as parcelas_vencidas,
       coalesce(t.maior_atraso, 0)      as maior_atraso,
       t.ultimo_pagamento,
       case when coalesce(t.tem_acordo, false) or t.ultimo_vencimento >= corte.data
              or t.codigo_cliente is null
            then case when coalesce(t.parcelas_vencidas, 0) > 0 then 'ativa_em_atraso' else 'ativa_em_dia' end
            else 'inadimplencia_antiga' end as carteira
from virtua.clientes c
left join tot t on t.codigo_cliente = c.codigo
cross join corte;

-- ---------- acesso ----------
-- RLS ligado e SEM políticas: a API pública do Supabase (anon/authenticated) não lê nem grava nada.
-- Só o app acessa, pela DATABASE_URL.
alter table virtua.usuarios  enable row level security;
alter table virtua.config    enable row level security;
alter table virtua.clientes  enable row level security;
alter table virtua.contratos enable row level security;
alter table virtua.acordos   enable row level security;
alter table virtua.parcelas  enable row level security;
alter table virtua.auditoria enable row level security;
revoke all on schema virtua from anon, authenticated;
revoke all on all tables in schema virtua from anon, authenticated;
