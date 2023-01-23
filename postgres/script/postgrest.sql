CREATE VIEW top_items AS SELECT 
    *, 
    (score - 1) / pow((EXTRACT(epoch FROM NOW() - time)/3600)+2, 1.8) AS score_top
FROM items
WHERE time > NOW() - interval '3' day AND type = 'story'
ORDER BY score_top DESC NULLS LAST
LIMIT 10;

create role web_anon nologin;

grant usage on schema public to web_anon;

grant select on public.items to web_anon;
grant select on public.top_items to web_anon;
