create role web_anon nologin;

grant usage on schema public to web_anon;
grant select on public.items to web_anon;