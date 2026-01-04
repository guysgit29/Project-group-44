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
import mysql.connector
from datetime import datetime


def create_user(first_name, last_name, email, password, birth_date, passport_number):
    mydb = mysql.connector.connect(
        host="localhost",
        user="root",
        password="rootroot",
        database="flytau",
        autocommit=True,
        auth_plugin='mysql_native_password'
    )

    cursor = mydb.cursor()

    # יצירת תאריך הרשמה אוטומטי
    current_reg_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # --- התיקון: שינוי מ-_eng ל-_en ---
    query = """
    INSERT INTO RegisteredUser 
    (email, first_name_en, last_name_en, birth_date, registration_date, passport_number, password) 
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    values = (email, first_name, last_name, birth_date, current_reg_date, passport_number, password)

    try:
        cursor.execute(query, values)
        mydb.commit()
        print("User created successfully!")
    except Exception as e:
        print(f"Error creating user: {e}")
    finally:
        cursor.close()
        mydb.close()

    return True