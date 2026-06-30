# 🌊 Nautilus Live Dashboard

דשבורד מסחר חי המציג **רק** עסקאות Nautilus, מופרד לחלוטין מ-Financial Runner.

## איך ההפרדה עובדת

Alpaca ו-Supabase לא מתייגים אילו עסקאות שייכות לאיזה מנוע מסחר — שני
המנועים (Nautilus + Financial Runner) חולקים אותו חשבון Alpaca ואותה
טבלת `trade_journal`. במקום לגעת בקוד הפרודקשן (`app_15_v2.py`,
`watchdog.py`) ולהוסיף שדה `source`, הדשבורד פותר את זה בשתי שכבות:

1. **פוזיציות חיות** — מסוננות לפי רשימת טיקרים שאתה מעדכן ידנית
   בממשק (תיבת טקסט), תואמת לרשימת ה-alerts הפעילה שלך ב-TradingView.
   מכיוון שאתה משנה טיקרים בתדירות, התיבה ניתנת לעריכה חופשית בכל רגע.

2. **היסטוריה** — הדשבורד **לא** קורא מ-`trade_journal` (שם אי אפשר
   להפריד בין המנועים). במקום זה הוא בונה יומן עצמי משלו בטבלה
   `nautilus_dashboard_log`, שנכתב אוטומטית בכל רענון. המשמעות: ההיסטוריה
   מתחילה **מהרגע שהפעלת את הדשבורד לראשונה** — לא מציגה עבר, אבל היא
   מדויקת ב-100% מאותה נקודה ואילך, ולא תלויה בתיוג שלא קיים.

## הגדרה ראשונית (פעם אחת)

1. כנס ל-Supabase SQL Editor והרץ את `setup_supabase.sql` — זה יוצר את
   טבלת `nautilus_dashboard_log`.

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# ערוך את secrets.toml עם המפתחות האמיתיים שלך
streamlit run app.py
```

## פריסה ל-Streamlit Cloud (כמו שאר המערכות שלך)

1. צור repo חדש ב-GitHub (למשל `nautilus-dashboard`)
2. העלה את כל הקבצים בתיקייה הזו (חוץ מ-secrets.toml האמיתי!)
3. כנס ל-[share.streamlit.io](https://share.streamlit.io)
4. "New app" → בחר את ה-repo → main file: `app.py`
5. ב-Settings → Secrets, הדבק:

```toml
ALPACA_API_KEY = "..."
ALPACA_API_SECRET = "..."
SUPABASE_URL = "https://bzwlizvgvhhymdlhhsnm.supabase.co"
SUPABASE_KEY = "..."
```

6. Deploy — תקבל URL קבוע

## שימוש יומיומי

- כל פעם שאתה מוסיף/מסיר alert ב-TradingView, עדכן את תיבת הטקסט
  "רשימת טיקרים פעילה" בדשבורד עם הרשימה הנוכחית.
- הדשבורד יציג רק פוזיציות שתואמות לרשימה — זה ה-Nautilus שלך, בלי
  עירוב עם Financial Runner.
- ההיסטוריה (טאב "יומן מעקב") נבנית אוטומטית בכל רענון — אין צורך
  לעשות כלום.

## מגבלות שצריך לדעת

- **לא משקף עבר** — אם תרצה לדעת מה Nautilus עשה לפני שהפעלת את
  הדשבורד, זה לא אפשרי בלי לחזור ולתייג ב-`database.py` (לא נעשה לפי
  בקשתך, כדי לא לסכן את הקוד החי).
- **חפיפת טיקרים** — אם אותו טיקר נסחר גם ב-Financial Runner וגם
  ב-Nautilus באותו זמן, שתי הפוזיציות יוצגו יחד תחת הסינון. בפועל זה
  נדיר כי שני המנועים פועלים על watchlists שונים ברובם.
- **תלות בעדכון ידני** — אם תשכח לעדכן את תיבת הטיקרים אחרי שינוי
  ב-TradingView, הסינון יהיה לא מדויק עד שתעדכן.

## הרחבות אפשריות (לעתיד)

- שמירת היסטוריית watchlist (מתי הוספת/הסרת כל טיקר) לצורך audit
- גרף equity curve מצטבר
- התראות Push כשפוזיציה נכנסת/נסגרת
