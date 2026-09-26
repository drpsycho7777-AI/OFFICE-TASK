# Office Ticket Management — Online Demo

A simple online ticket/task tracking demo for a loan/DSA office.

## Demo accounts

**Manager**
- Username: `manager`
- Password: `1234`

**Employees**
- `rahul` / `1234`
- `priya` / `1234`
- `amit` / `1234`

## Deploy to Streamlit Community Cloud

1. Create a new GitHub repository.
2. Upload the contents of this folder to the repository.
3. Sign in to Streamlit Community Cloud using GitHub.
4. Click **Create app**.
5. Select your repository.
6. Set the main file path to `app.py`.
7. Click **Deploy**.

The deployed app will receive a `streamlit.app` web address.

## Demo features

- Manager and employee logins
- Create/assign tickets
- Customer/company name
- Loan type
- Required amount
- Banking/GST/Financial surrogate
- Multiple Bank/NBFC logins under one ticket
- Priority and due date
- Employee lender-by-lender updates
- Login Done / Pending / Rejected / Documents Required / Re-login
- Login/Application ID
- Employee remarks
- Progress bar
- Activity history
- Manager dashboard
- Employee dashboard
- Report download

## Important demo limitation

This version uses SQLite stored inside the app's server filesystem. It is suitable for a manager demonstration, but cloud restarts/redeployments can reset local data.

For production office use, move the database to a persistent hosted database such as PostgreSQL/Supabase before relying on it for real cases.
