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
            password="rootroot",
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
    # יצירת החיבור
    mydb = mysql.connector.connect(
        host="localhost",
        user="root",
        password="rootroot",
        database="flytau",
        autocommit=True
    )

    # יצירת ה-cursor (זו השורה שהייתה חסרה לך)
    cursor = mydb.cursor()

    # שאילתת SQL להכנסת נתונים
    query = "INSERT INTO RegisteredUser (first_name, last_name, email, password) VALUES (%s, %s, %s, %s)"
    # שים לב: שיניתי את שם הטבלה ל-RegisteredUser כי זה מה שמופיע בקוד הלוגין שלך,
    # במקום users. אם הטבלה ב-DB שלך היא users, תחזיר את זה ל-users.

    values = (first_name, last_name, email, password)

    try:
        cursor.execute(query, values)
        mydb.commit()  # תיקון: שימוש ב-mydb במקום ב-conn
    except Exception as e:
        print(f"Error creating user: {e}")
    finally:
        # סגירת החיבורים בצורה מסודרת
        cursor.close()
        mydb.close()  # תיקון: שימוש ב-mydb במקום ב-conn

    return True