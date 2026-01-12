from database import DB
from models.flight import Flight


class Employee:
    def __init__(self, id, first_name_he, last_name_he, start_date,
                 city, street, house_number):
        self.id = id
        self.first_name_he = first_name_he
        self.last_name_he = last_name_he
        self.start_date = start_date
        self.city = city
        self.street = street
        self.house_number = house_number


class Manager(Employee):
    def __init__(self, id, first_name_he, last_name_he, start_date,
                 city, street, house_number):
        super().__init__(id, first_name_he, last_name_he, start_date, city, street, house_number)

    @staticmethod
    def login(emp_id: int, password: str):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name_he, last_name_he, start_date,
                       city, street, house_number
                FROM Manager
                WHERE id = %s AND password = %s
            """, (int(emp_id), password))

            row = cursor.fetchone()
            if not row:
                return None

            return Manager(
                row["id"],
                row["first_name_he"],
                row["last_name_he"],
                row.get("start_date"),
                row.get("city"),
                row.get("street"),
                row.get("house_number")
            )


class Pilot(Employee):
    def __init__(self, id, first_name_he, last_name_he, start_date,
                 city, street, house_number, big_aircraft_cert=None):
        super().__init__(id, first_name_he, last_name_he, start_date, city, street, house_number)
        self.big_aircraft_cert = big_aircraft_cert

    # =========================
    # ✅ LOCATION (DEFAULT TLV)
    # =========================
    @staticmethod
    def get_current_location_before(pilot_id: int, before_dt) -> str:
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

    # =========================
    # LIST / ASSIGNED
    # =========================
    @staticmethod
    def list_all(flight_number: int | None = None):
        """
        אם flight_number לא נשלח -> מחזיר את כל הטייסים.
        אם כן נשלח -> מחזיר רק טייסים זמינים + מתאימים (הסמכה + בלי חפיפה + בלי שיבוץ כפול + מיקום).
        """
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name_he, last_name_he, start_date,
                       city, street, house_number, big_aircraft_cert
                FROM Pilot
                ORDER BY id
            """)
            rows = cursor.fetchall() or []

        pilots = [Pilot(
            r["id"], r["first_name_he"], r["last_name_he"],
            r.get("start_date"), r.get("city"), r.get("street"), r.get("house_number"),
            r.get("big_aircraft_cert")
        ) for r in rows]

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

    @staticmethod
    def get_assigned_for_flight(flight_number: int):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT p.*
                FROM Pilot p
                JOIN pilots_on_flights pof
                  ON p.id = pof.id
                WHERE pof.flight_number = %s
                ORDER BY p.id
            """, (int(flight_number),))
            rows = cursor.fetchall() or []

        return [Pilot(
            r["id"], r["first_name_he"], r["last_name_he"],
            r.get("start_date"), r.get("city"), r.get("street"), r.get("house_number"),
            r.get("big_aircraft_cert")
        ) for r in rows]

    # =========
    # ✅ RULES
    # =========
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
                  AND f.flight_status IN ('Active','Delayed')
                  AND (
                        %s < COALESCE(f.arrival_time, ADDTIME(f.departure_time, fl.length_minutes))
                    AND f.departure_time < %s
                  )
                LIMIT 1
            """, (int(pilot_id), int(flight_number), new_start, new_end))

            return cursor.fetchone() is not None

    @staticmethod
    def assign_to_flight(pilot_id: int, flight_number: int) -> tuple[bool, str]:
        pilot_id = int(pilot_id)
        flight_number = int(flight_number)

        # 0) limit
        required = Flight.get_required_crew_counts(flight_number)
        if Flight.count_assigned_pilots(flight_number) >= int(required["pilots"]):
            return False, "כבר שובצו מספיק טייסים לטיסה הזו"

        # 1) cert
        if not Pilot._cert_ok_for_flight(pilot_id, flight_number):
            return False, "הטייס לא מוסמך למטוס גדול בטיסה הזו"

        # 2) overlap
        if Pilot._has_overlap(pilot_id, flight_number):
            return False, "לא ניתן לשבץ: יש חפיפה עם טיסה אחרת של הטייס"

        # 3) location
        if not Pilot._location_ok_for_flight(pilot_id, flight_number):
            return False, "לא ניתן לשבץ: הטייס לא נמצא במוצא הטיסה"

        with DB.get_cursor() as cursor:
            # 4) already assigned
            cursor.execute("""
                SELECT 1
                FROM pilots_on_flights
                WHERE id = %s AND flight_number = %s
                LIMIT 1
            """, (pilot_id, flight_number))
            if cursor.fetchone():
                return False, "הטייס כבר משובץ לטיסה הזו"

            # 5) insert
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


class FlightAttendant(Employee):
    def __init__(self, id, first_name_he, last_name_he, start_date,
                 city, street, house_number, big_aircraft_cert=None):
        super().__init__(id, first_name_he, last_name_he, start_date, city, street, house_number)
        self.big_aircraft_cert = big_aircraft_cert

    # =========================
    # ✅ LOCATION (DEFAULT TLV)
    # =========================
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
    def list_all(flight_number: int | None = None):
        """
        אם flight_number לא נשלח -> מחזיר את כל הדיילים.
        אם כן נשלח -> מחזיר רק דיילים זמינים + מתאימים (הסמכה + בלי חפיפה + בלי שיבוץ כפול + מיקום).
        """
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, first_name_he, last_name_he, start_date,
                       city, street, house_number, big_aircraft_cert
                FROM FlightAttendant
                ORDER BY id
            """)
            rows = cursor.fetchall() or []

        attendants = [FlightAttendant(
            r["id"], r["first_name_he"], r["last_name_he"],
            r.get("start_date"), r.get("city"), r.get("street"), r.get("house_number"),
            r.get("big_aircraft_cert")
        ) for r in rows]

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

    @staticmethod
    def get_assigned_for_flight(flight_number: int):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT fa.*
                FROM FlightAttendant fa
                JOIN flightattendants_on_flights fof
                  ON fa.id = fof.id
                WHERE fof.flight_number = %s
                ORDER BY fa.id
            """, (int(flight_number),))
            rows = cursor.fetchall() or []

        return [FlightAttendant(
            r["id"], r["first_name_he"], r["last_name_he"],
            r.get("start_date"), r.get("city"), r.get("street"), r.get("house_number"),
            r.get("big_aircraft_cert")
        ) for r in rows]

    # =========
    # ✅ RULES
    # =========
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
                  AND f.flight_status IN ('Active','Delayed')
                  AND (
                        %s < COALESCE(f.arrival_time, ADDTIME(f.departure_time, fl.length_minutes))
                    AND f.departure_time < %s
                  )
                LIMIT 1
            """, (int(attendant_id), int(flight_number), new_start, new_end))

            return cursor.fetchone() is not None

    @staticmethod
    def assign_to_flight(attendant_id: int, flight_number: int) -> tuple[bool, str]:
        attendant_id = int(attendant_id)
        flight_number = int(flight_number)

        # 0) limit
        required = Flight.get_required_crew_counts(flight_number)
        if Flight.count_assigned_attendants(flight_number) >= int(required["attendants"]):
            return False, "כבר שובצו מספיק דיילים לטיסה הזו"

        # 1) cert
        if not FlightAttendant._cert_ok_for_flight(attendant_id, flight_number):
            return False, "הדייל/ת לא מוסמך/ת למטוס גדול בטיסה הזו"

        # 2) overlap
        if FlightAttendant._has_overlap(attendant_id, flight_number):
            return False, "לא ניתן לשבץ: יש חפיפה עם טיסה אחרת של הדייל/ת"

        # 3) location
        if not FlightAttendant._location_ok_for_flight(attendant_id, flight_number):
            return False, "לא ניתן לשבץ: הדייל/ת לא נמצא/ת במוצא הטיסה"

        with DB.get_cursor() as cursor:
            # 4) already assigned
            cursor.execute("""
                SELECT 1
                FROM flightattendants_on_flights
                WHERE id = %s AND flight_number = %s
                LIMIT 1
            """, (attendant_id, flight_number))
            if cursor.fetchone():
                return False, "הדייל/ת כבר משובץ/ת לטיסה הזו"

            # 5) insert
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
