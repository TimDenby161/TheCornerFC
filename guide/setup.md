# Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in API_FOOTBALL_KEY and DATABASE_URL
python -m thecornerfc status    # checks the API key and shows quota
python -m thecornerfc init-db   # creates the tables in Supabase
```

For `DATABASE_URL`, go to the Supabase dashboard, click **Connect**, and copy the **Session pooler** string. The direct connection only works over IPv6.
