from __future__ import annotations
from datetime import datetime
from database import DB
from models.flight import Flight
import re



class Employee:
    def __init__(self, id, first_name_he, last_name_he, start_date, city, street, house_number):
        self.id = id
        self.first_name_he = first_name_he
        self.last_name_he = last_name_he
        self.start_date = start_date
        self.city = city
        self.street = street
        self.house_number = house_number


class Manager(Employee):
    def __init__(self, id, first_name_he, last_name_he, start_date, city, street, house_number):
        super().__init__(id, first_name_he, last_name_he, start_date, city, street, house_number)

    @staticmethod
    def login(emp_id: int, password: str):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name_he, last_name_he, start_date, city, street, house_number
                FROM Manager
                WHERE id = %s AND password = %s
            """, (int(emp_id), password))
            row = cursor.fetchone()
            if not row:
                return None

            return Manager(
                row["id"], row["first_name_he"], row["last_name_he"],
                row.get("start_date"), row.get("city"),
                row.get("street"), row.get("house_number")
            )


# ==========================================================
# PILOT
# ==========================================================

class Pilot(Employee):
    def __init__(self, id, first_name_he, last_name_he, start_date, city, street, house_number, big_aircraft_cert=0):
        super().__init__(id, first_name_he, last_name_he, start_date, city, street, house_number)
        self.big_aircraft_cert = int(big_aircraft_cert or 0)

    # -------------------------
    # Assigned / List
    # -------------------------

    @staticmethod
    def get_assigned_for_flight(flight_number: int):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT p.*
                FROM Pilot p
                JOIN pilots_on_flights pof ON p.id = pof.id
                WHERE pof.flight_number = %s
                ORDER BY p.id
            """, (int(flight_number),))
            rows = cursor.fetchall() or []

        return [
            Pilot(
                r["id"], r["first_name_he"], r["last_name_he"],
                r.get("start_date"), r.get("city"), r.get("street"), r.get("house_number"),
                r.get("big_aircraft_cert")
            )
            for r in rows
        ]

    @staticmethod
    def list_all(flight_number: int | None = None):
        """
        אם flight_number לא נשלח -> כל הטייסים.
        אם כן -> רק טייסים זמינים + מתאימים (הסמכה + בלי חפיפה + בלי שיבוץ כפול + מיקום).
        """
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name_he, last_name_he, start_date, city, street, house_number, big_aircraft_cert
                FROM Pilot
                ORDER BY id
            """)
            rows = cursor.fetchall() or []

        pilots = [
            Pilot(
                r["id"], r["first_name_he"], r["last_name_he"],
                r.get("start_date"), r.get("city"), r.get("street"), r.get("house_number"),
                r.get("big_aircraft_cert")
            )
            for r in rows
        ]

        if not flight_number:
            return pilots

        flight_number = int(flight_number)
        assigned_ids = {p.id for p in Pilot.get_assigned_for_flight(flight_number)}

        filtered = []
        for p in pilots:
            if p.id in assigned_ids:
                continue
            if not Pilot._cert_ok_for_flight(p.id, flight_number):
                continue
            if Pilot._has_overlap(p.id, flight_number):
                continue
            if not Pilot._location_ok_for_flight(p.id, flight_number):
                continue
            filtered.append(p)

        return filtered

    # -------------------------
    # Location / Rules
    # -------------------------

    @staticmethod
    def get_current_location_before(pilot_id: int, before_dt) -> str:
        """
        יעד אחרון בטיסות Completed לפני before_dt, אחרת TLV.
        """
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT f.destination
                FROM pilots_on_flights pof
                JOIN Flight f ON f.flight_number = pof.flight_number
                WHERE pof.id = %s
                  AND f.arrival_time IS NOT NULL
                  AND f.arrival_time < %s
                  AND f.flight_status = 'Completed'
                ORDER BY f.arrival_time DESC
                LIMIT 1
            """, (int(pilot_id), before_dt))
            row = cursor.fetchone()

        return row["destination"] if row else "TLV"

    @staticmethod
    def _location_ok_for_flight(pilot_id: int, flight_number: int) -> bool:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT origin, departure_time
                FROM Flight
                WHERE flight_number = %s
            """, (int(flight_number),))
            flight = cursor.fetchone()

        if not flight or not flight.get("departure_time") or not flight.get("origin"):
            return False

        current_location = Pilot.get_current_location_before(int(pilot_id), flight["departure_time"])
        return current_location == flight["origin"]

    @staticmethod
    def _cert_ok_for_flight(pilot_id: int, flight_number: int) -> bool:
        size = (Flight.get_aircraft_size_for_flight(flight_number) or "").strip().lower()
        if not size:
            return False
        if size != "large":
            return True

        with DB.get_cursor() as cursor:
            cursor.execute("SELECT big_aircraft_cert FROM Pilot WHERE id = %s", (int(pilot_id),))
            row = cursor.fetchone()

        return bool(row and int(row.get("big_aircraft_cert") or 0) == 1)

    @staticmethod
    def _has_overlap(pilot_id: int, flight_number: int) -> bool:
        new_start, new_end = Flight.get_flight_window(flight_number)
        if not new_start or not new_end:
            return True

        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT 1
                FROM pilots_on_flights pof
                JOIN Flight f ON f.flight_number = pof.flight_number
                LEFT JOIN FlightLength fl
                    ON fl.origin = f.origin AND fl.destination = f.destination
                WHERE pof.id = %s
                  AND pof.flight_number <> %s
                  AND f.flight_status IN ('Active','Full','Delayed')
                  AND (
                        %s < COALESCE(f.arrival_time, ADDTIME(f.departure_time, fl.length_minutes))
                    AND f.departure_time < %s
                  )
                LIMIT 1
            """, (int(pilot_id), int(flight_number), new_start, new_end))

            return cursor.fetchone() is not None

    # -------------------------
    # Assign / Remove (existing flight manage)
    # -------------------------

    @staticmethod
    def assign_to_flight(pilot_id: int, flight_number: int) -> tuple[bool, str]:
        pilot_id = int(pilot_id)
        flight_number = int(flight_number)

        required = Flight.get_required_crew_counts(flight_number)
        if Flight.count_assigned_pilots(flight_number) >= int(required["pilots"]):
            return False, "כבר שובצו מספיק טייסים לטיסה הזו"

        if not Pilot._cert_ok_for_flight(pilot_id, flight_number):
            return False, "הטייס לא מוסמך למטוס גדול בטיסה הזו"

        if Pilot._has_overlap(pilot_id, flight_number):
            return False, "לא ניתן לשבץ: יש חפיפה עם טיסה אחרת של הטייס"

        if not Pilot._location_ok_for_flight(pilot_id, flight_number):
            return False, "לא ניתן לשבץ: הטייס לא נמצא במוצא הטיסה"

        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT 1
                FROM pilots_on_flights
                WHERE id = %s AND flight_number = %s
                LIMIT 1
            """, (pilot_id, flight_number))
            if cursor.fetchone():
                return False, "הטייס כבר משובץ לטיסה הזו"

            cursor.execute("""
                INSERT INTO pilots_on_flights (id, flight_number)
                VALUES (%s, %s)
            """, (pilot_id, flight_number))

        return True, "שיבוץ טייס בוצע בהצלחה"

    @staticmethod
    def remove_from_flight(pilot_id: int, flight_number: int) -> tuple[bool, str]:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                DELETE FROM pilots_on_flights
                WHERE id = %s AND flight_number = %s
            """, (int(pilot_id), int(flight_number)))

            if cursor.rowcount > 0:
                return True, "הטייס הוסר מהטיסה"
            return False, "הטייס לא היה משובץ לטיסה הזו"

    # ==========================================================
    # ✅ For NEW flight creation (availability by time window)
    # ==========================================================

    @staticmethod
    def list_available_for_new_flight(origin: str, dep_dt: datetime, arr_dt: datetime, aircraft_size: str):
        """
        מחזיר רשימת טייסים זמינים לטיסה חדשה לפי:
        - הסמכה (אם Large)
        - מיקום (יעד אחרון Completed לפני dep_dt, אחרת TLV) חייב להיות origin
        - בלי חפיפה מול טיסות Active/Full/Delayed
        """
        origin = (origin or "").strip()
        aircraft_size = (aircraft_size or "").strip().lower()

        with DB.get_cursor() as cursor:
            sql = """
                SELECT p.*
                FROM Pilot p
                WHERE 1=1
            """
            if aircraft_size == "large":
                sql += " AND p.big_aircraft_cert = 1"
            sql += " ORDER BY p.id"

            cursor.execute(sql)
            pilots = cursor.fetchall() or []

        available = []
        for p in pilots:
            pid = int(p["id"])

            current_loc = Pilot.get_current_location_before(pid, dep_dt)
            if current_loc != origin:
                continue

            with DB.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 1
                    FROM pilots_on_flights pof
                    JOIN Flight f ON f.flight_number = pof.flight_number
                    LEFT JOIN FlightLength fl ON fl.origin=f.origin AND fl.destination=f.destination
                    WHERE pof.id=%s
                      AND f.flight_status IN ('Active','Full','Delayed')
                      AND (
                          %s < COALESCE(f.arrival_time, ADDTIME(f.departure_time, fl.length_minutes))
                          AND f.departure_time < %s
                      )
                    LIMIT 1
                """, (pid, dep_dt, arr_dt))
                if cursor.fetchone():
                    continue

            available.append(p)

        return available


# ==========================================================
# FLIGHT ATTENDANT
# ==========================================================

class FlightAttendant(Employee):
    def __init__(self, id, first_name_he, last_name_he, start_date, city, street, house_number, big_aircraft_cert=0):
        super().__init__(id, first_name_he, last_name_he, start_date, city, street, house_number)
        self.big_aircraft_cert = int(big_aircraft_cert or 0)

    @staticmethod
    def get_assigned_for_flight(flight_number: int):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT fa.*
                FROM FlightAttendant fa
                JOIN flightattendants_on_flights fof ON fa.id = fof.id
                WHERE fof.flight_number = %s
                ORDER BY fa.id
            """, (int(flight_number),))
            rows = cursor.fetchall() or []

        return [
            FlightAttendant(
                r["id"], r["first_name_he"], r["last_name_he"],
                r.get("start_date"), r.get("city"), r.get("street"), r.get("house_number"),
                r.get("big_aircraft_cert")
            )
            for r in rows
        ]

    @staticmethod
    def list_all(flight_number: int | None = None):
        """
        אם flight_number לא נשלח -> כל הדיילים.
        אם כן -> רק דיילים זמינים + מתאימים (הסמכה + בלי חפיפה + בלי שיבוץ כפול + מיקום).
        """
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name_he, last_name_he, start_date, city, street, house_number, big_aircraft_cert
                FROM FlightAttendant
                ORDER BY id
            """)
            rows = cursor.fetchall() or []

        attendants = [
            FlightAttendant(
                r["id"], r["first_name_he"], r["last_name_he"],
                r.get("start_date"), r.get("city"), r.get("street"), r.get("house_number"),
                r.get("big_aircraft_cert")
            )
            for r in rows
        ]

        if not flight_number:
            return attendants

        flight_number = int(flight_number)
        assigned_ids = {a.id for a in FlightAttendant.get_assigned_for_flight(flight_number)}

        filtered = []
        for a in attendants:
            if a.id in assigned_ids:
                continue
            if not FlightAttendant._cert_ok_for_flight(a.id, flight_number):
                continue
            if FlightAttendant._has_overlap(a.id, flight_number):
                continue
            if not FlightAttendant._location_ok_for_flight(a.id, flight_number):
                continue
            filtered.append(a)

        return filtered

    # -------------------------
    # Location / Rules
    # -------------------------

    @staticmethod
    def get_current_location_before(attendant_id: int, before_dt) -> str:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT f.destination
                FROM flightattendants_on_flights fof
                JOIN Flight f ON f.flight_number = fof.flight_number
                WHERE fof.id = %s
                  AND f.arrival_time IS NOT NULL
                  AND f.arrival_time < %s
                  AND f.flight_status = 'Completed'
                ORDER BY f.arrival_time DESC
                LIMIT 1
            """, (int(attendant_id), before_dt))
            row = cursor.fetchone()

        return row["destination"] if row else "TLV"

    @staticmethod
    def _location_ok_for_flight(attendant_id: int, flight_number: int) -> bool:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT origin, departure_time
                FROM Flight
                WHERE flight_number = %s
            """, (int(flight_number),))
            flight = cursor.fetchone()

        if not flight or not flight.get("departure_time") or not flight.get("origin"):
            return False

        current_location = FlightAttendant.get_current_location_before(int(attendant_id), flight["departure_time"])
        return current_location == flight["origin"]

    @staticmethod
    def _cert_ok_for_flight(attendant_id: int, flight_number: int) -> bool:
        size = (Flight.get_aircraft_size_for_flight(flight_number) or "").strip().lower()
        if not size:
            return False
        if size != "large":
            return True

        with DB.get_cursor() as cursor:
            cursor.execute("SELECT big_aircraft_cert FROM FlightAttendant WHERE id = %s", (int(attendant_id),))
            row = cursor.fetchone()

        return bool(row and int(row.get("big_aircraft_cert") or 0) == 1)

    @staticmethod
    def _has_overlap(attendant_id: int, flight_number: int) -> bool:
        new_start, new_end = Flight.get_flight_window(flight_number)
        if not new_start or not new_end:
            return True

        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT 1
                FROM flightattendants_on_flights fof
                JOIN Flight f ON f.flight_number = fof.flight_number
                LEFT JOIN FlightLength fl
                    ON fl.origin = f.origin AND fl.destination = f.destination
                WHERE fof.id = %s
                  AND fof.flight_number <> %s
                  AND f.flight_status IN ('Active','Full','Delayed')
                  AND (
                        %s < COALESCE(f.arrival_time, ADDTIME(f.departure_time, fl.length_minutes))
                    AND f.departure_time < %s
                  )
                LIMIT 1
            """, (int(attendant_id), int(flight_number), new_start, new_end))

            return cursor.fetchone() is not None

    # -------------------------
    # Assign / Remove
    # -------------------------

    @staticmethod
    def assign_to_flight(attendant_id: int, flight_number: int) -> tuple[bool, str]:
        attendant_id = int(attendant_id)
        flight_number = int(flight_number)

        required = Flight.get_required_crew_counts(flight_number)
        if Flight.count_assigned_attendants(flight_number) >= int(required["attendants"]):
            return False, "כבר שובצו מספיק דיילים לטיסה הזו"

        if not FlightAttendant._cert_ok_for_flight(attendant_id, flight_number):
            return False, "הדייל/ת לא מוסמך/ת למטוס גדול בטיסה הזו"

        if FlightAttendant._has_overlap(attendant_id, flight_number):
            return False, "לא ניתן לשבץ: יש חפיפה עם טיסה אחרת של הדייל/ת"

        if not FlightAttendant._location_ok_for_flight(attendant_id, flight_number):
            return False, "לא ניתן לשבץ: הדייל/ת לא נמצא/ת במוצא הטיסה"

        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT 1
                FROM flightattendants_on_flights
                WHERE id = %s AND flight_number = %s
                LIMIT 1
            """, (attendant_id, flight_number))
            if cursor.fetchone():
                return False, "הדייל/ת כבר משובץ/ת לטיסה הזו"

            cursor.execute("""
                INSERT INTO flightattendants_on_flights (id, flight_number)
                VALUES (%s, %s)
            """, (attendant_id, flight_number))

        return True, "שיבוץ דייל/ת בוצע בהצלחה"

    @staticmethod
    def remove_from_flight(attendant_id: int, flight_number: int) -> tuple[bool, str]:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                DELETE FROM flightattendants_on_flights
                WHERE id = %s AND flight_number = %s
            """, (int(attendant_id), int(flight_number)))

            if cursor.rowcount > 0:
                return True, "הדייל/ת הוסר/ה מהטיסה"
            return False, "הדייל/ת לא היה/תה משובץ/ת לטיסה הזו"

    # ==========================================================
    # ✅ For NEW flight creation (availability by time window)
    # ==========================================================

    @staticmethod
    def list_available_for_new_flight(origin: str, dep_dt: datetime, arr_dt: datetime, aircraft_size: str):
        origin = (origin or "").strip()
        aircraft_size = (aircraft_size or "").strip().lower()

        with DB.get_cursor() as cursor:
            sql = """
                SELECT fa.*
                FROM FlightAttendant fa
                WHERE 1=1
            """
            if aircraft_size == "large":
                sql += " AND fa.big_aircraft_cert = 1"
            sql += " ORDER BY fa.id"

            cursor.execute(sql)
            attendants = cursor.fetchall() or []

        available = []
        for a in attendants:
            aid = int(a["id"])

            current_loc = FlightAttendant.get_current_location_before(aid, dep_dt)
            if current_loc != origin:
                continue

            with DB.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 1
                    FROM flightattendants_on_flights fof
                    JOIN Flight f ON f.flight_number = fof.flight_number
                    LEFT JOIN FlightLength fl ON fl.origin=f.origin AND fl.destination=f.destination
                    WHERE fof.id=%s
                      AND f.flight_status IN ('Active','Full','Delayed')
                      AND (
                          %s < COALESCE(f.arrival_time, ADDTIME(f.departure_time, fl.length_minutes))
                          AND f.departure_time < %s
                      )
                    LIMIT 1
                """, (aid, dep_dt, arr_dt))
                if cursor.fetchone():
                    continue

            available.append(a)

        return available

from datetime import datetime
from database import DB


_PHONE_RE = re.compile(r"^[0-9+\- ]{6,20}$")  # גמיש: 05X-XXXXXXX / +972...

class StaffService:
    """
    Service לצפייה והוספה של אנשי צוות.
    """

    @staticmethod
    def get_staff_tables():
        """
        מחזיר שתי רשימות dicts:
        pilots, attendants
        """
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name_he, last_name_he, start_date, city, street, house_number,
                       phone_num, big_aircraft_cert
                FROM Pilot
                ORDER BY id
            """)
            pilots = cursor.fetchall() or []

            cursor.execute("""
                SELECT id, first_name_he, last_name_he, start_date, city, street, house_number,
                       phone_num, big_aircraft_cert
                FROM FlightAttendant
                ORDER BY id
            """)
            attendants = cursor.fetchall() or []

        return pilots, attendants

    @staticmethod
    def add_staff_member(staff_type: str, form) -> tuple[bool, str | None]:
        """
        staff_type: 'pilot' / 'attendant'
        form: request.form
        מחזיר (ok, error_msg)
        """
        staff_type = (staff_type or "").strip().lower()
        if staff_type not in ("pilot", "attendant"):
            return False, "סוג איש צוות לא תקין"

        table = "Pilot" if staff_type == "pilot" else "FlightAttendant"

        # ---- Read ----
        id_raw = (form.get("id") or "").strip()
        first_name_he = (form.get("first_name_he") or "").strip()
        last_name_he = (form.get("last_name_he") or "").strip()
        start_date = (form.get("start_date") or "").strip()  # YYYY-MM-DD
        city = (form.get("city") or "").strip()
        street = (form.get("street") or "").strip()
        house_number_raw = (form.get("house_number") or "").strip()
        phone_num = (form.get("phone_num") or "").strip()
        big_aircraft_cert_raw = (form.get("big_aircraft_cert") or "0").strip()

        # ---- Validate ----
        if not id_raw.isdigit():
            return False, "תעודת עובד חייבת להיות מספר"
        emp_id = int(id_raw)

        if not first_name_he or not last_name_he:
            return False, "שם פרטי ושם משפחה הם שדות חובה"

        if not house_number_raw.isdigit():
            return False, "מספר בית חייב להיות מספר"
        house_number = int(house_number_raw)

        # phone optional, אבל אם מילאו אז נאמת פורמט בסיסי
        if phone_num:
            if not _PHONE_RE.match(phone_num):
                return False, "מספר טלפון לא תקין"

        # start_date יכול להיות ריק => NULL
        start_date_val = None
        if start_date:
            try:
                datetime.strptime(start_date, "%Y-%m-%d")
                start_date_val = start_date
            except ValueError:
                return False, "תאריך התחלה חייב להיות בפורמט YYYY-MM-DD"

        big_aircraft_cert = 1 if str(big_aircraft_cert_raw) in ("1", "true", "True", "on") else 0

        # ---- Insert ----
        with DB.get_cursor() as cursor:
            cursor.execute(f"SELECT 1 FROM {table} WHERE id=%s LIMIT 1", (emp_id,))
            if cursor.fetchone():
                return False, "כבר קיים איש צוות עם תעודת עובד זו"

            cursor.execute(
                f"""
                INSERT INTO {table}
                    (id, first_name_he, last_name_he, start_date, city, street, house_number,
                     phone_num, big_aircraft_cert)
                VALUES
                    (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (emp_id, first_name_he, last_name_he, start_date_val, city, street, house_number,
                 phone_num, big_aircraft_cert),
            )

        return True, None