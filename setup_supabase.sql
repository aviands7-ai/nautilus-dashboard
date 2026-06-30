-- הרץ את זה פעם אחת ב-Supabase SQL Editor לפני הפעלת הדשבורד.
-- הטבלה הזו עצמאית לחלוטין מ-trade_journal ומ-tv_positions —
-- היא קיימת רק כדי שהדשבורד יוכל לבנות היסטוריה של Nautilus
-- בלי תלות בתיוג source שלא קיים במערכות הקיימות.

create table if not exists nautilus_dashboard_log (
    id bigint generated always as identity primary key,
    logged_at timestamptz not null default now(),
    watchlist text not null,
    open_positions_count integer not null default 0,
    total_unrealized_pl numeric not null default 0,
    positions_snapshot jsonb
);

-- אינדקס לשאילתות לפי זמן (היסטוריה, גרפים)
create index if not exists idx_nautilus_log_logged_at
    on nautilus_dashboard_log (logged_at);

-- RLS (Row Level Security) — תואם למדיניות שכבר קיימת בשאר הטבלאות שלך
alter table nautilus_dashboard_log enable row level security;

create policy "Allow all access to nautilus_dashboard_log"
    on nautilus_dashboard_log
    for all
    using (true)
    with check (true);
