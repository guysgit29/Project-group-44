from datetime import date
from database import DB

class Aircraft:
    def __init__(self, aircraft_id, manufacturer, size):
        self.id = aircraft_id
        self.manufacturer = manufacturer
        self.size = size  # 'Big' / 'Small'  (בעמודה DB: aircraft_size)

    @staticmethod
    def get_by_id(aircraft_id):
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM Aircraft WHERE aircraft_id = %s", (aircraft_id,))
            row = cursor.fetchone()
            if row:
                # FIX: העמודה נקראת aircraft_size (לא size)
                return Aircraft(row['aircraft_id'], row['manufacturer'], row['aircraft_size'])
            return None

    @staticmethod
    def get_all():
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT aircraft_id, manufacturer, purchase_date, aircraft_size
                FROM Aircraft
                ORDER BY aircraft_id DESC
            """)
            return cursor.fetchall() or []

    # ------------------------
    # מחלקות + מספר מושבים
    # ------------------------
    @staticmethod
    def get_classes_for_aircrafts(aircraft_ids):
        if not aircraft_ids:
            return {}

        placeholders = ",".join(["%s"] * len(aircraft_ids))

        with DB.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT
                    C.aircraft_id,
                    C.class_type,
                    C.total_rows,
                    C.total_columns,
                    COUNT(S.row_num) AS seats_count
                FROM Class C
                LEFT JOIN Seat S
                  ON S.aircraft_id = C.aircraft_id
                 AND S.class_type = C.class_type
                WHERE C.aircraft_id IN ({placeholders})
                GROUP BY C.aircraft_id, C.class_type, C.total_rows, C.total_columns
                ORDER BY C.aircraft_id DESC, C.class_type
            """, tuple(aircraft_ids))

            rows = cursor.fetchall() or []

        result = {}
        for r in rows:
            aid = int(r["aircraft_id"])
            result.setdefault(aid, []).append(r)

        return result

    # ------------------------
    # היסטוריית טיסות
    # ------------------------
    @staticmethod
    def get_flights_for_aircrafts(aircraft_ids):
        if not aircraft_ids:
            return {}

        placeholders = ",".join(["%s"] * len(aircraft_ids))

        with DB.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT
                    aircraft_id,
                    flight_number,
                    origin,
                    destination,
                    departure_time,
                    arrival_time,
                    flight_status
                FROM Flight
                WHERE aircraft_id IN ({placeholders})
                ORDER BY aircraft_id DESC, departure_time DESC
            """, tuple(aircraft_ids))

            rows = cursor.fetchall() or []

        result = {}
        for r in rows:
            aid = int(r["aircraft_id"])
            result.setdefault(aid, []).append(r)

        return result

    # ------------------------
    # Alias אם קראת לזה אחרת ב-app.py
    # ------------------------
    @staticmethod
    def get_flights_history_for_aircrafts(aircraft_ids):
        # כדי שלא תיפול אם ב-app.py אתה קורא בשם הזה
        return Aircraft.get_flights_for_aircrafts(aircraft_ids)

    @staticmethod
    def get_filtered(aircraft_id=None, manufacturer=None, size=None):
        query = """
            SELECT aircraft_id, manufacturer, purchase_date, aircraft_size
            FROM Aircraft
            WHERE 1=1
        """
        params = []

        if aircraft_id:
            query += " AND aircraft_id LIKE %s"
            params.append(f"%{aircraft_id}%")

        if manufacturer:
            query += " AND manufacturer = %s"
            params.append(manufacturer)

        if size:
            query += " AND aircraft_size = %s"
            params.append(size)

        query += " ORDER BY aircraft_id DESC"

        with DB.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall() or []

    @staticmethod
    def get_next_aircraft_id() -> int:
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(aircraft_id), 100) AS max_id FROM Aircraft")
            row = cursor.fetchone() or {}
            return int(row.get("max_id") or 100) + 1

    @staticmethod
    def create_aircraft_with_seats(
            manufacturer: str,
            purchase_date: str,
            economy_rows: int,
            economy_cols: int,
            business_rows: int | None,
            business_cols: int | None,
    ) -> int:
        """
        Creates:
        - Aircraft row (aircraft_id auto via MAX+1)
        - Class rows (Economy always, Business optional)
        - Seat rows for each class
        Size rule:
        - if Business provided -> Big
        - else -> Small
        Returns aircraft_id
        """

        aircraft_id = Aircraft.get_next_aircraft_id()

        has_business = (
                business_rows is not None and business_cols is not None
                and int(business_rows) > 0 and int(business_cols) > 0
        )

        aircraft_size = "Big" if has_business else "Small"

        with DB.get_cursor() as cursor:
            # 1) insert aircraft
            cursor.execute(
                """
                INSERT INTO Aircraft (aircraft_id, manufacturer, purchase_date, aircraft_size)
                VALUES (%s, %s, %s, %s)
                """,
                (aircraft_id, manufacturer, purchase_date, aircraft_size),
            )

            # 2) insert Economy class
            cursor.execute(
                """
                INSERT INTO Class (aircraft_id, class_type, total_rows, total_columns)
                VALUES (%s, %s, %s, %s)
                """,
                (aircraft_id, "Economy", int(economy_rows), int(economy_cols)),
            )

            # 3) insert Economy seats
            for r in range(1, int(economy_rows) + 1):
                for c in range(1, int(economy_cols) + 1):
                    cursor.execute(
                        """
                        INSERT INTO Seat (aircraft_id, class_type, row_num, column_number)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (aircraft_id, "Economy", r, c),
                    )

            # 4) Business optional
            if has_business:
                cursor.execute(
                    """
                    INSERT INTO Class (aircraft_id, class_type, total_rows, total_columns)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (aircraft_id, "Business", int(business_rows), int(business_cols)),
                )

                for r in range(1, int(business_rows) + 1):
                    for c in range(1, int(business_cols) + 1):
                        cursor.execute(
                            """
                            INSERT INTO Seat (aircraft_id, class_type, row_num, column_number)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (aircraft_id, "Business", r, c),
                        )

        return aircraft_id