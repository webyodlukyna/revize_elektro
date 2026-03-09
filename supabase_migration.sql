-- vytvořil lukyn.sifty@gmail.com copyright 2025
-- Supabase migration for revize_elektro
-- Spusťte v Supabase SQL Editoru.

begin;

create table if not exists public.zakaznici (
    id bigserial primary key,
    jmeno text not null,
    telefon text,
    email text,
    adresa text,
    poznamka text,
    created_at timestamp without time zone not null default now()
);

create table if not exists public.spolecnosti (
    id bigserial primary key,
    nazev text not null,
    ico text,
    kontakt text,
    telefon text,
    email text,
    adresa text,
    poznamka text,
    created_at timestamp without time zone not null default now()
);

alter table public.revize
    add column if not exists zakaznik_id bigint,
    add column if not exists spolecnost_id bigint;

create index if not exists idx_revize_zakaznik_id on public.revize (zakaznik_id);
create index if not exists idx_revize_spolecnost_id on public.revize (spolecnost_id);
create index if not exists idx_zakaznici_jmeno on public.zakaznici (jmeno);
create index if not exists idx_spolecnosti_nazev on public.spolecnosti (nazev);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'revize_zakaznik_id_fkey'
    ) THEN
        ALTER TABLE public.revize
            ADD CONSTRAINT revize_zakaznik_id_fkey
            FOREIGN KEY (zakaznik_id)
            REFERENCES public.zakaznici(id)
            ON DELETE SET NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'revize_spolecnost_id_fkey'
    ) THEN
        ALTER TABLE public.revize
            ADD CONSTRAINT revize_spolecnost_id_fkey
            FOREIGN KEY (spolecnost_id)
            REFERENCES public.spolecnosti(id)
            ON DELETE SET NULL;
    END IF;
END
$$;

commit;
