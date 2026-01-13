from __future__ import annotations
from datetime import datetime, timedelta
from database import DB


class Flight:
    def __init__(self, flight_number, aircraft_id, origin, destination, departure, arrival, status):
        self.flight_number = flight_number
        self.aircraft_id = aircraft_id
        self.origin = origin
        self.destination = destination
        self.departure = departure
        self.arrival = arrival
        self.status = status

    # -------------------------
    # Customer helpers
    # -------------------------

    @staticmethod
    def get_all_origins_and_destinations():
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT origin FROM Flight ORDER BY origin ASC")
            origins = cursor.fetchall()

            cursor.execute("SELECT DISTINCT destination FROM Flight ORDER BY destination ASC")
            destinations = cursor.fetchall()

            return origins, destinations

    @staticmethod
    def sync_completed_flights() -> int:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                UPDATE Flight
                SET flight_status = 'Completed'
                WHERE arrival_time IS NOT NULL
                  AND arrival_time < NOW()
                  AND flight_status IN ('Active','Full','Delayed')
            """)
            return cursor.rowcount

    @staticmethod
    def search(origin, destination):
        Flight.sync_completed_flights()

        query = """
            SELECT *
            FROM Flight
            WHERE origin = %s
              AND destination = %s
              AND flight_status IN ('Active', 'Full')
            ORDER BY departure_time ASC
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query, (origin, destination))
            return cursor.fetchall()

    @staticmethod
    def get_seat_map(flight_number: int):
        with DB.get_cursor() as cursor:
            cursor.execute(
                "SELECT aircraft_id FROM Flight WHERE flight_number = %s",
                (int(flight_number),)
            )
            f = cursor.fetchone()
            if not f:
                return []

            aircraft_id = f["aircraft_id"]

            query = """
                SELECT
                    s.row_num,
                    s.column_number,
                    s.class_type,
                    CASE
                        WHEN t.booking_id IS NULL THEN 1
                        ELSE 0
                    END AS available,
                    cof.class_price
                FROM Seat s
                LEFT JOIN Classes_on_Flights cof
                  ON cof.flight_number = %s
                 AND cof.class_type = s.class_type
                 AND cof.aircraft_id = s.aircraft_id
                LEFT JOIN Ticket t
                  ON t.flight_number = %s
                 AND t.class_type = s.class_type
                 AND t.row_num = s.row_num
                 AND t.column_number = s.column_number
                WHERE s.aircraft_id = %s
                ORDER BY
                    FIELD(s.class_type, 'First', 'Business', 'Economy'),
                    s.row_num,
                    s.column_number
            """
            cursor.execute(query, (int(flight_number), int(flight_number), aircraft_id))
            return cursor.fetchall()

    @staticmethod
    def update_status_by_capacity(flight_number: int) -> str | None:
        if not flight_number:
            return None

        with DB.get_cursor() as cursor:
            cursor.execute(
                "SELECT aircraft_id, flight_status FROM Flight WHERE flight_number = %s",
                (int(flight_number),)
            )
            f = cursor.fetchone()
            if not f or f.get("aircraft_id") is None:
                return None

            current_status = (f.get("flight_status") or "").strip()

            # ✅ לא משנים סטטוסים סופיים
            if current_status in ("Completed", "Canceled"):
                return current_status

            aircraft_id = int(f["aircraft_id"])

            cursor.execute(
                "SELECT COUNT(*) AS total_seats FROM Seat WHERE aircraft_id = %s",
                (aircraft_id,)
            )
            total = int((cursor.fetchone() or {}).get("total_seats") or 0)

            cursor.execute(
                "SELECT COUNT(*) AS sold_seats FROM Ticket WHERE flight_number = %s",
                (int(flight_number),)
            )
            sold = int((cursor.fetchone() or {}).get("sold_seats") or 0)

            new_status = "Full" if total > 0 and sold >= total else "Active"

            if current_status != new_status:
                cursor.execute(
                    "UPDATE Flight SET flight_status = %s WHERE flight_number = %s",
                    (new_status, int(flight_number))
                )

            return new_status

    # -------------------------
    # Manager helpers
    # -------------------------

    @staticmethod
    def list_for_manager(selected_status: str = "", aircraft_id: int | None = None):
        query = """
            SELECT
                flight_number,
                aircraft_id,
                origin,
                destination,
                departure_time,
                arrival_time,
                flight_status
            FROM Flight
        """

        where = []
        params = []

        selected_status = (selected_status or "").strip()
        if selected_status:
            where.append("flight_status = %s")
            params.append(selected_status)

        if aircraft_id is not None:
            where.append("aircraft_id = %s")
            params.append(int(aircraft_id))

        if where:
            query += " WHERE " + " AND ".join(where)

        query += " ORDER BY departure_time DESC"

        with DB.get_cursor() as cursor:
            cursor.execute(query, tuple(params))
            return cursor.fetchall()

    @staticmethod
    def get_by_number(flight_number: int):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    flight_number,
                    aircraft_id,
                    origin,
                    destination,
                    departure_time,
                    arrival_time,
                    flight_status
                FROM Flight
                WHERE flight_number = %s
            """, (int(flight_number),))
            return cursor.fetchone()

    @staticmethod
    def get_aircraft_by_id(aircraft_id: int):
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM Aircraft WHERE aircraft_id = %s", (int(aircraft_id),))
            return cursor.fetchone()

    @staticmethod
    def get_all_aircraft_ids():
        """לדרופדאון סינון במסך manager_flights."""
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT aircraft_id
                FROM Flight
                WHERE aircraft_id IS NOT NULL
                ORDER BY aircraft_id ASC
            """)
            rows = cursor.fetchall() or []
        return [r["aircraft_id"] for r in rows]

    @staticmethod
    def get_aircraft_size_for_flight(flight_number: int) -> str | None:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT a.aircraft_size
                FROM Flight f
                JOIN Aircraft a ON a.aircraft_id = f.aircraft_id
                WHERE f.flight_number = %s
            """, (int(flight_number),))
            row = cursor.fetchone()
            return row.get("aircraft_size") if row else None

    @staticmethod
    def get_flight_window(flight_number: int):
        """
        start = departure_time
        end   = arrival_time אם יש, אחרת departure_time + FlightLength.length_minutes
        (לבדיקת חפיפות לצוות)
        """
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    f.departure_time AS start_time,
                    COALESCE(
                        f.arrival_time,
                        ADDTIME(f.departure_time, fl.length_minutes)
                    ) AS end_time
                FROM Flight f
                LEFT JOIN FlightLength fl
                    ON fl.origin = f.origin AND fl.destination = f.destination
                WHERE f.flight_number = %s
            """, (int(flight_number),))
            row = cursor.fetchone()

        if not row:
            return None, None

        return row.get("start_time"), row.get("end_time")

    # -------------------------
    # Crew capacity rules (NO buffer)
    # -------------------------

    @staticmethod
    def get_required_crew_counts(flight_number: int) -> dict:
        """
        Large: 3 pilots, 6 attendants
        Small: 2 pilots, 3 attendants
        """
        size = (Flight.get_aircraft_size_for_flight(flight_number) or "").strip().lower()
        if size == "large":
            return {"pilots": 3, "attendants": 6}
        return {"pilots": 2, "attendants": 3}

    @staticmethod
    def count_assigned_pilots(flight_number: int) -> int:
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS c FROM pilots_on_flights WHERE flight_number=%s", (int(flight_number),))
            row = cursor.fetchone() or {}
        return int(row.get("c") or 0)

    @staticmethod
    def count_assigned_attendants(flight_number: int) -> int:
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS c FROM flightattendants_on_flights WHERE flight_number=%s", (int(flight_number),))
            row = cursor.fetchone() or {}
        return int(row.get("c") or 0)

    # ==========================================================
    # ✅ Helpers for "Create New Flight" (manager_flight_create)
    # ==========================================================

    @staticmethod
    def get_all_aircrafts():
        """למסך יצירת טיסה חדשה."""
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT aircraft_id, aircraft_size, manufacturer
                FROM Aircraft
                ORDER BY aircraft_id
            """)
            return cursor.fetchall() or []

    @staticmethod
    def get_all_routes():
        """נתיבים קיימים מתוך FlightLength."""
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT origin, destination, length_minutes
                FROM FlightLength
                ORDER BY origin, destination
            """)
            return cursor.fetchall() or []

    @staticmethod
    def get_all_route_origins():
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT origin
                FROM FlightLength
                ORDER BY origin
            """)
            rows = cursor.fetchall() or []
        return [r["origin"] for r in rows]

    @staticmethod
    def get_destinations_for_origin(origin: str):
        origin = (origin or "").strip()
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT destination
                FROM FlightLength
                WHERE origin=%s
                ORDER BY destination
            """, (origin,))
            rows = cursor.fetchall() or []
        return [r["destination"] for r in rows]

    @staticmethod
    def get_route_length(origin: str, destination: str):
        """מחזיר TIME של MySQL או None."""
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT length_minutes
                FROM FlightLength
                WHERE origin=%s AND destination=%s
            """, (origin, destination))
            row = cursor.fetchone()
        return row["length_minutes"] if row else None

    @staticmethod
    def get_route_duration_seconds(origin: str, destination: str) -> int:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT TIME_TO_SEC(length_minutes) AS sec
                FROM FlightLength
                WHERE origin=%s AND destination=%s
            """, (origin, destination))
            row = cursor.fetchone() or {}
        return int(row.get("sec") or 0)

    @staticmethod
    def get_aircraft_size(aircraft_id: int) -> str:
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT aircraft_size FROM Aircraft WHERE aircraft_id=%s", (int(aircraft_id),))
            row = cursor.fetchone()
        return (row["aircraft_size"] or "").strip().lower() if row else ""

    @staticmethod
    def flight_number_exists(flight_number: int) -> bool:
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT 1 FROM Flight WHERE flight_number=%s LIMIT 1", (int(flight_number),))
            return cursor.fetchone() is not None

    @staticmethod
    def create_flight(
        flight_number: int,
        aircraft_id: int,
        origin: str,
        destination: str,
        departure_time: datetime,
        flight_status: str = "Active",
    ) -> tuple[bool, str]:
        """
        יוצר טיסה רק אם הנתיב קיים ב-FlightLength.
        arrival_time ייקבע ע"י ה-trigger שלך (before insert).
        """

        origin = (origin or "").strip()
        destination = (destination or "").strip()
        flight_status = (flight_status or "Active").strip() or "Active"

        if not origin or not destination:
            return False, "חובה לבחור שדה מקור ושדה יעד"

        if not isinstance(departure_time, datetime):
            return False, "תאריך/שעת המראה לא תקין"

        # ✅ נתיב חייב להיות קיים
        length = Flight.get_route_length(origin, destination)
        if not length:
            return False, "לא ניתן להוסיף טיסה לנתיב שלא קיים. קודם הוסף קו טיסה (FlightLength)."

        # ✅ מעל 6 שעות => חייב Large
        duration_sec = Flight.get_route_duration_seconds(origin, destination)
        size = Flight.get_aircraft_size(int(aircraft_id))
        if duration_sec > 6 * 3600 and size != "large":
            return False, "טיסה מעל 6 שעות חייבת להיות עם מטוס Large"

        # ✅ מספר טיסה ייחודי
        if Flight.flight_number_exists(int(flight_number)):
            return False, "מספר טיסה כבר קיים במערכת"

        with DB.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO Flight (flight_number, aircraft_id, origin, destination, departure_time, flight_status)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (int(flight_number), int(aircraft_id), origin, destination, departure_time, flight_status))

        return True, "טיסה נוצרה בהצלחה"

    # ==========================================================
    # ✅ NEW: Cancel rules for manager (72 hours)
    # ==========================================================

    @staticmethod
    def can_manager_cancel(flight_number: int) -> bool:
        """
        ניתן לבטל טיסה רק אם ההמראה בעוד 72 שעות או יותר
        """
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT departure_time, flight_status
                FROM Flight
                WHERE flight_number = %s
            """, (int(flight_number),))
            f = cursor.fetchone()

        if not f:
            return False

        status = (f["flight_status"] or "").strip()
        if status in ("Completed", "Canceled"):
            return False

        dep = f.get("departure_time")
        if not dep:
            return False

        return dep - datetime.now() >= timedelta(hours=72)

    @staticmethod
    def cancel_flight(flight_number: int) -> tuple[bool, str]:
        if not flight_number:
            return False, "מספר טיסה חסר"

        flight_number = int(flight_number)

        # חוק 72 שעות
        if not Flight.can_manager_cancel(flight_number):
            return False, "לא ניתן לבטל טיסה פחות מ-72 שעות לפני ההמראה"

        with DB.get_cursor() as cursor:
            cursor.execute(
                "SELECT flight_status FROM Flight WHERE flight_number = %s",
                (flight_number,)
            )
            f = cursor.fetchone()
            if not f:
                return False, "הטיסה לא קיימת"

            current_status = (f.get("flight_status") or "").strip()

            if current_status == "Completed":
                return False, "לא ניתן לבטל טיסה שהושלמה"

            if current_status == "Canceled":
                return True, "הטיסה כבר בוטלה"

            # 🔥 כאן השינוי האמיתי
            cursor.execute(
                "UPDATE Flight SET flight_status = 'Canceled' WHERE flight_number = %s",
                (flight_number,)
            )

            cursor.execute("""
                UPDATE Booking
                SET price = 0,
                    booking_status = 'Canceled by Manager'
                WHERE flight_number = %s
            """, (flight_number,))

        return True, "הטיסה בוטלה וההזמנות עודכנו"


    # ==========================================================
    # ✅ Manage Flight Routes (FlightLength)
    # ==========================================================

    @staticmethod
    def search_routes(origin: str = "", destination: str = ""):
        origin = (origin or "").strip()
        destination = (destination or "").strip()

        query = """
            SELECT origin, destination, length_minutes
            FROM FlightLength
        """
        where = []
        params = []

        if origin:
            where.append("origin = %s")
            params.append(origin)
        if destination:
            where.append("destination = %s")
            params.append(destination)

        if where:
            query += " WHERE " + " AND ".join(where)

        query += " ORDER BY origin, destination"

        with DB.get_cursor() as cursor:
            cursor.execute(query, tuple(params))
            return cursor.fetchall() or []

    @staticmethod
    def create_route(origin: str, destination: str, length_minutes: str) -> tuple[bool, str | None]:
        origin = (origin or "").strip()
        destination = (destination or "").strip()
        length_minutes = (length_minutes or "").strip()

        if not origin or not destination or not length_minutes:
            return False, "יש למלא מקור, יעד ואורך טיסה"

        if origin == destination:
            return False, "מקור ויעד לא יכולים להיות זהים"

        # אופציונלי: בדיקת פורמט בסיסית ל-TIME (מאפשר HH:MM או HH:MM:SS)
        parts = length_minutes.split(":")
        if len(parts) not in (2, 3):
            return False, "פורמט אורך טיסה לא תקין. השתמש HH:MM או HH:MM:SS"

        try:
            with DB.get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO FlightLength (origin, destination, length_minutes)
                    VALUES (%s, %s, %s)
                    """,
                    (origin, destination, length_minutes),
                )
            return True, None
        except Exception as e:
            msg = str(e)
            if "Duplicate" in msg or "1062" in msg:
                return False, "קו כזה כבר קיים (אותו מקור ואותו יעד)"
            return False, f"שגיאת DB: {msg}"

        # --- Step 1 dropdowns (FlightLength) ---

    @staticmethod
    def get_route_origins_distinct():
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT origin FROM FlightLength ORDER BY origin")
            rows = cursor.fetchall() or []
        return [r["origin"] for r in rows]

    @staticmethod
    def get_route_destinations_distinct():
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT destination FROM FlightLength ORDER BY destination")
            rows = cursor.fetchall() or []
        return [r["destination"] for r in rows]

    @staticmethod
    def get_route_info(origin: str, destination: str):
        """
        returns dict: { length_time, duration_sec }
        """
        origin = (origin or "").strip()
        destination = (destination or "").strip()
        with DB.get_cursor() as cursor:
            cursor.execute("""
                   SELECT
                       length_minutes AS length_time,
                       TIME_TO_SEC(length_minutes) AS duration_sec
                   FROM FlightLength
                   WHERE origin=%s AND destination=%s
               """, (origin, destination))
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "length_time": row.get("length_time"),
            "duration_sec": int(row.get("duration_sec") or 0)
        }

    @staticmethod
    def compute_arrival(dep_dt: datetime, origin: str, destination: str):
        """
        מחשב arrival (לתצוגה בלבד). בפועל ה-TRIGGER ישלים את arrival_time ב-INSERT.
        """
        with DB.get_cursor() as cursor:
            cursor.execute("""
                   SELECT ADDTIME(%s, length_minutes) AS arrival_dt
                   FROM FlightLength
                   WHERE origin=%s AND destination=%s
               """, (dep_dt, origin, destination))
            row = cursor.fetchone() or {}
        return row.get("arrival_dt")

    @staticmethod
    def list_available_pilots_for_new_flight(origin: str, dep_dt: datetime, require_large: bool):
        origin = (origin or "").strip()
        cert_clause = "AND p.big_aircraft_cert = 1" if require_large else ""

        query = f"""
           SELECT
               p.id,
               p.first_name_he,
               p.last_name_he,
               p.big_aircraft_cert,
               lastf.last_destination,
               lastf.last_end_time
           FROM Pilot p
           LEFT JOIN (
               SELECT
                   x.id,
                   SUBSTRING_INDEX(
                       GROUP_CONCAT(x.destination ORDER BY x.end_time DESC SEPARATOR ','), ',', 1
                   ) AS last_destination,
                   MAX(x.end_time) AS last_end_time
               FROM (
                   SELECT
                       pf.id,
                       f.destination,
                       COALESCE(
                           f.arrival_time,
                           ADDTIME(f.departure_time, fl.length_minutes)
                       ) AS end_time
                   FROM Pilots_on_Flights pf
                   JOIN Flight f ON f.flight_number = pf.flight_number
                   LEFT JOIN FlightLength fl
                       ON fl.origin=f.origin AND fl.destination=f.destination
                   WHERE f.departure_time < %s
               ) x
               WHERE x.end_time < %s
               GROUP BY x.id
           ) lastf ON lastf.id = p.id
           WHERE 1=1
             {cert_clause}
             AND (
                 lastf.id IS NULL
                 OR lastf.last_destination = %s
             )
           ORDER BY p.id
           """
        with DB.get_cursor() as cursor:
            cursor.execute(query, (dep_dt, dep_dt, origin))
            return cursor.fetchall() or []

    @staticmethod
    def list_available_attendants_for_new_flight(origin: str, dep_dt: datetime, require_large: bool):
        origin = (origin or "").strip()
        cert_clause = "AND fa.big_aircraft_cert = 1" if require_large else ""

        query = f"""
           SELECT
               fa.id,
               fa.first_name_he,
               fa.last_name_he,
               fa.big_aircraft_cert,
               lastf.last_destination,
               lastf.last_end_time
           FROM FlightAttendant fa
           LEFT JOIN (
               SELECT
                   x.id,
                   SUBSTRING_INDEX(
                       GROUP_CONCAT(x.destination ORDER BY x.end_time DESC SEPARATOR ','), ',', 1
                   ) AS last_destination,
                   MAX(x.end_time) AS last_end_time
               FROM (
                   SELECT
                       ff.id,
                       f.destination,
                       COALESCE(
                           f.arrival_time,
                           ADDTIME(f.departure_time, fl.length_minutes)
                       ) AS end_time
                   FROM FlightAttendants_on_Flights ff
                   JOIN Flight f ON f.flight_number = ff.flight_number
                   LEFT JOIN FlightLength fl
                       ON fl.origin=f.origin AND fl.destination=f.destination
                   WHERE f.departure_time < %s
               ) x
               WHERE x.end_time < %s
               GROUP BY x.id
           ) lastf ON lastf.id = fa.id
           WHERE 1=1
             {cert_clause}
             AND (
                 lastf.id IS NULL
                 OR lastf.last_destination = %s
             )
           ORDER BY fa.id
           """
        with DB.get_cursor() as cursor:
            cursor.execute(query, (dep_dt, dep_dt, origin))
            return cursor.fetchall() or []

    @staticmethod
    def generate_next_flight_number() -> int:
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(flight_number), 1000) AS m FROM Flight")
            row = cursor.fetchone() or {}
        return int(row.get("m") or 1000) + 1

    @staticmethod
    def list_available_aircrafts_for_route(origin: str, dep_dt: datetime, require_large: bool):
        """
        מחזיר מטוסים זמינים לשיבוץ:
        1) המטוס לא יכול להיות בטיסה שחופפת (הטיסה האחרונה שלו חייבת להסתיים לפני dep_dt)
        2) היעד האחרון של המטוס חייב להיות origin
        3) אם אין למטוס היסטוריה בכלל -> מניחים שהוא ב-TLV, ולכן מותר רק אם origin == 'TLV'
        4) אם require_large=True -> רק Large
        """
        origin = (origin or "").strip()

        size_clause = " AND LOWER(a.aircraft_size) = 'large' " if require_large else ""

        query = f"""
            SELECT
                a.aircraft_id,
                a.aircraft_size,
                a.manufacturer,
                lf.last_destination,
                lf.last_end_time
            FROM Aircraft a
            LEFT JOIN (
                SELECT
                    t.aircraft_id,
                    SUBSTRING_INDEX(
                        GROUP_CONCAT(t.destination ORDER BY t.end_time DESC SEPARATOR ','), ',', 1
                    ) AS last_destination,
                    MAX(t.end_time) AS last_end_time
                FROM (
                    SELECT
                        f.aircraft_id,
                        f.destination,
                        COALESCE(
                            f.arrival_time,
                            ADDTIME(f.departure_time, fl.length_minutes)
                        ) AS end_time
                    FROM Flight f
                    LEFT JOIN FlightLength fl
                      ON fl.origin = f.origin AND fl.destination = f.destination
                    WHERE f.aircraft_id IS NOT NULL
                      AND f.departure_time < %s
                ) t
                WHERE t.end_time <= %s
                GROUP BY t.aircraft_id
            ) lf ON lf.aircraft_id = a.aircraft_id
            WHERE 1=1
              {size_clause}
              AND (
                    lf.aircraft_id IS NULL AND %s = 'TLV'
                    OR lf.last_destination = %s
                  )
            ORDER BY a.aircraft_id ASC
        """

        # placeholders: 4
        params = (dep_dt, dep_dt, origin, origin)

        with DB.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall() or []

    @staticmethod
    def get_pilots_by_ids(ids):
        if not ids:
            return []
        placeholders = ",".join(["%s"] * len(ids))
        q = f"""
               SELECT id, first_name_he, last_name_he
               FROM Pilot
               WHERE id IN ({placeholders})
               ORDER BY id
           """
        with DB.get_cursor() as cursor:
            cursor.execute(q, tuple(ids))
            return cursor.fetchall()

    @staticmethod
    def get_attendants_by_ids(ids):
        if not ids:
            return []
        placeholders = ",".join(["%s"] * len(ids))
        q = f"""
               SELECT id, first_name_he, last_name_he
               FROM FlightAttendant
               WHERE id IN ({placeholders})
               ORDER BY id
           """
        with DB.get_cursor() as cursor:
            cursor.execute(q, tuple(ids))
            return cursor.fetchall()

    @staticmethod
    def get_all_airports_distinct():
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT airport FROM (
                    SELECT origin AS airport FROM FlightLength
                    UNION
                    SELECT destination AS airport FROM FlightLength
                ) AS all_airports
                ORDER BY airport
            """)
            return [row["airport"] for row in cursor.fetchall()]