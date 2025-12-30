import mysql.connector
from contextlib import contextmanager


@contextmanager
def db_cur():
    mydb = None
    cursor = None
    try:
        mydb = mysql.connector.connect(
            host="localhost",
            user="root",
            password="root",
            database="theater_db",
            autocommit=True
        )
        cursor = mydb.cursor()
        yield cursor
    except mysql.connector.Error as err:
        raise err
    finally:
        if cursor: cursor.close()
        if mydb: mydb.close()


import mysql.connector  # או מה שאת משתמשת בו לחיבור


# פונקציה לדוגמה לשמירת משתמש
def create_user(first_name, last_name, email, password):
    # כאן את מתחברת ל-DB שלך
    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='YOUR_PASSWORD',
        database='YOUR_DB_NAME'
    )
    cursor = conn.cursor()

    # שאילתת SQL להכנסת נתונים
    query = "INSERT INTO users (first_name, last_name, email, password) VALUES (%s, %s, %s, %s)"
    values = (first_name, last_name, email, password)

    cursor.execute(query, values)
    conn.commit()  # חשוב מאוד! בלי זה השינוי לא יישמר ב-DB

    cursor.close()
    conn.close()
    return True