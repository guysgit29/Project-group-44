import mysql.connector
from contextlib import contextmanager
from datetime import datetime

# =================================================
# 1. פונקציית החיבור הבסיסית (מה שביקשת)
# =================================================
def get_connection():
    """יוצר ומחזיר אובייקט חיבור לבסיס הנתונים - המקום היחיד שבו מגדירים סיסמה ומסד"""
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="rootroot",
        database="flytau",
        autocommit=True,
        auth_plugin='mysql_native_password'
    )

# =================================================
# 2. ה-Context Manager (משתמש ב-get_connection)
# =================================================
@contextmanager
def db_cur():
    """מנהל את פתיחת וסגירת ה-Cursor והחיבור באופן אוטומטי"""
    mydb = None
    cursor = None
    try:
        mydb = get_connection()
        # dictionary=True מאפשר לנו לעבוד עם שמות עמודות (כמו row['email']) במקום אינדקסים
        cursor = mydb.cursor(dictionary=True)
        yield cursor
    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
        raise err
    finally:
        if cursor: cursor.close()
        if mydb: mydb.close()

# =================================================
# 3. פונקציות עזר עסקיות
# =================================================

def create_user(first_name, last_name, email, password, birth_date, passport_number):
    """פונקציה לשמירת משתמש רשום חדש"""
    current_reg_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    query = """
    INSERT INTO RegisteredUser 
    (email, first_name_en, last_name_en, birth_date, registration_date, passport_number, password) 
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    values = (email, first_name, last_name, birth_date, current_reg_date, passport_number, password)

    try:
        with db_cur() as cursor:
            cursor.execute(query, values)
            print(f"User {email} created successfully!")
            return True
    except Exception as e:
        print(f"Error creating user: {e}")
        return False