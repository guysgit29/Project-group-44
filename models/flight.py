from __future__ import annotations
from datetime import datetime, timedelta
from database import DB
class Flight:
    def __init__(self, flight_number, aircraft_id, origin, destination, departure, arrival, status):  # Represents one flight entity (core fields only)
        self.flight_number = flight_number
        self.aircraft_id = aircraft_id
        self.origin = origin
        self.destination = destination
        self.departure = departure
        self.arrival = arrival
        self.status = status

    @staticmethod
    def get_all_origins_and_destinations():  # Returns distinct origins and destinations for the public search dropdowns
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT origin FROM Flight ORDER BY origin ASC")
            origins = cursor.fetchall()
            cursor.execute("SELECT DISTINCT destination FROM Flight ORDER BY destination ASC")
            destinations = cursor.fetchall()
            return origins, destinations

    @staticmethod
    def sync_completed_flights() -> int:  # Marks flights as Completed when arrival_time is in the past
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
    def search(origin, destination):  # Searches Active/Full flights for a given route (and syncs Completed first)
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
            return cursor.fetchall() or []

    @staticmethod
    def get_seat_map(flight_number: int):  # Returns seat grid with availability and per-class price for a flight
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT aircraft_id FROM Flight WHERE flight_number = %s", (int(flight_number),))
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
            return cursor.fetchall() or []

    @staticmethod
    def update_status_by_capacity(flight_number: int) -> str | None:  # Recomputes flight_status as Full/Active based on tickets count vs seats
        if not flight_number:
            return None
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT aircraft_id, flight_status FROM Flight WHERE flight_number = %s", (int(flight_number),))
            f = cursor.fetchone()
            if not f or f.get("aircraft_id") is None:
                return None
            current_status = (f.get("flight_status") or "").strip()
            if current_status in ("Completed", "Canceled"):
                return current_status
            aircraft_id = int(f["aircraft_id"])
            cursor.execute("SELECT COUNT(*) AS total_seats FROM Seat WHERE aircraft_id = %s", (aircraft_id,))
            total = int((cursor.fetchone() or {}).get("total_seats") or 0)
            cursor.execute("SELECT COUNT(*) AS sold_seats FROM Ticket WHERE flight_number = %s", (int(flight_number),))
            sold = int((cursor.fetchone() or {}).get("sold_seats") or 0)
            new_status = "Full" if total > 0 and sold >= total else "Active"
            if current_status != new_status:
                cursor.execute("UPDATE Flight SET flight_status = %s WHERE flight_number = %s", (new_status, int(flight_number)))
            return new_status

    @staticmethod
    def list_for_manager(selected_status: str = "", aircraft_id: int | None = None):  # Lists flights for manager screen with optional filters
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
            return cursor.fetchall() or []

    @staticmethod
    def manager_list_page_data(selected_status: str = "", aircraft_id: int | None = None):
        """Prepares manager_flights page data.

        Returns (flights, aircraft_ids) where each flight row includes a boolean 'can_cancel'.
        """
        Flight.sync_completed_flights()
        flights = Flight.list_for_manager(selected_status, aircraft_id)
        for f in flights:
            st = (f.get("flight_status") or "").strip()
            f["can_cancel"] = False if st in ("Completed", "Canceled") else Flight.can_manager_cancel(f["flight_number"])
        aircraft_ids = Flight.get_all_aircraft_ids()
        return flights, aircraft_ids

    @staticmethod
    def manager_manage_context(flight_number: int):
        """Builds the full context dict for manager_flight_manage.html (GET).

        Encapsulates the bulk of page data shaping so app.py stays thin.
        Returns None if the flight does not exist.
        """
        from models.employees import Pilot, FlightAttendant

        Flight.sync_completed_flights()
        flight = Flight.get_by_number(int(flight_number))
        if not flight:
            return None

        aircraft = Flight.get_aircraft_by_id(flight["aircraft_id"])

        flight["aircraft_size"] = Flight.get_aircraft_size_for_flight(int(flight_number))
        st = (flight.get("flight_status") or "").strip()

        assigned_pilots = Pilot.get_assigned_for_flight(int(flight_number))
        assigned_attendants = FlightAttendant.get_assigned_for_flight(int(flight_number))

        all_pilots = Pilot.list_all(int(flight_number))
        all_attendants = FlightAttendant.list_all(int(flight_number))

        required = Flight.get_required_crew_counts(int(flight_number))
        assigned_counts = {"pilots": len(assigned_pilots), "attendants": len(assigned_attendants)}
        missing_counts = {
            "pilots": max(0, int(required["pilots"]) - assigned_counts["pilots"]),
            "attendants": max(0, int(required["attendants"]) - assigned_counts["attendants"]),
        }

        now = datetime.now()
        dep = flight.get("departure_time")
        if isinstance(dep, str):
            try:
                dep = datetime.strptime(dep, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                dep = None

        is_active_like = st in ("Active", "Full")
        is_departing_soon = False
        can_cancel = False

        if is_active_like and isinstance(dep, datetime):
            time_left = dep - now
            is_departing_soon = timedelta(seconds=0) < time_left <= timedelta(hours=72)
            can_cancel = time_left > timedelta(hours=72)

        return {
            "flight": flight,
            "aircraft": aircraft,
            "assigned_pilots": assigned_pilots,
            "assigned_attendants": assigned_attendants,
            "all_pilots": all_pilots,
            "all_attendants": all_attendants,
            "required": required,
            "assigned_counts": assigned_counts,
            "missing_counts": missing_counts,
            "can_cancel": can_cancel,
            "is_departing_soon": is_departing_soon,
        }

    @staticmethod
    def get_by_number(flight_number: int):  # Fetches a single flight row by flight_number
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
    def get_aircraft_by_id(aircraft_id: int):  # Fetches aircraft row by aircraft_id
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM Aircraft WHERE aircraft_id = %s", (int(aircraft_id),))
            return cursor.fetchone()

    @staticmethod
    def get_all_aircraft_ids():  # Returns aircraft_id list for manager flights filter dropdown
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
    def get_aircraft_size_for_flight(flight_number: int) -> str | None:  # Returns aircraft_size for a given flight_number
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
    def get_flight_window(flight_number: int):  # Returns (start,end) datetime window for overlap checks (arrival or computed duration)
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

    @staticmethod
    def get_required_crew_counts(flight_number: int) -> dict:  # Returns required pilots/attendants counts based on aircraft size (Large/Small)
        size = (Flight.get_aircraft_size_for_flight(flight_number) or "").strip().lower()
        if size == "large":
            return {"pilots": 3, "attendants": 6}
        return {"pilots": 2, "attendants": 3}

    @staticmethod
    def count_assigned_pilots(flight_number: int) -> int:  # Counts pilots assigned to a flight
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS c FROM pilots_on_flights WHERE flight_number=%s", (int(flight_number),))
            row = cursor.fetchone() or {}
        return int(row.get("c") or 0)

    @staticmethod
    def count_assigned_attendants(flight_number: int) -> int:  # Counts attendants assigned to a flight
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS c FROM flightattendants_on_flights WHERE flight_number=%s", (int(flight_number),))
            row = cursor.fetchone() or {}
        return int(row.get("c") or 0)

    @staticmethod
    def get_all_aircrafts():  # Returns all aircrafts for the manager “create flight” flow
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT aircraft_id, aircraft_size, manufacturer
                FROM Aircraft
                ORDER BY aircraft_id
            """)
            return cursor.fetchall() or []

    @staticmethod
    def get_all_routes():  # Returns all FlightLength routes for manager route selection
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT origin, destination, length_minutes
                FROM FlightLength
                ORDER BY origin, destination
            """)
            return cursor.fetchall() or []

    @staticmethod
    def get_all_route_origins():  # Returns distinct route origins from FlightLength
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT origin FROM FlightLength ORDER BY origin")
            rows = cursor.fetchall() or []
        return [r["origin"] for r in rows]

    @staticmethod
    def get_destinations_for_origin(origin: str):  # Returns destinations for a given origin from FlightLength
        origin = (origin or "").strip()
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT destination FROM FlightLength WHERE origin=%s ORDER BY destination", (origin,))
            rows = cursor.fetchall() or []
        return [r["destination"] for r in rows]

    @staticmethod
    def get_route_length(origin: str, destination: str):  # Returns FlightLength.length_minutes TIME for a route (or None)
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT length_minutes FROM FlightLength WHERE origin=%s AND destination=%s", (origin, destination))
            row = cursor.fetchone()
        return row["length_minutes"] if row else None

    @staticmethod
    def get_route_duration_seconds(origin: str, destination: str) -> int:  # Returns route duration in seconds from FlightLength
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT TIME_TO_SEC(length_minutes) AS sec
                FROM FlightLength
                WHERE origin=%s AND destination=%s
            """, (origin, destination))
            row = cursor.fetchone() or {}
        return int(row.get("sec") or 0)

    @staticmethod
    def get_aircraft_size(aircraft_id: int) -> str:  # Returns aircraft_size (lowercase) for an aircraft_id
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT aircraft_size FROM Aircraft WHERE aircraft_id=%s", (int(aircraft_id),))
            row = cursor.fetchone()
        return (row["aircraft_size"] or "").strip().lower() if row else ""

    @staticmethod
    def flight_number_exists(flight_number: int) -> bool:  # Checks whether a flight_number already exists
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT 1 FROM Flight WHERE flight_number=%s LIMIT 1", (int(flight_number),))
            return cursor.fetchone() is not None

    @staticmethod
    def create_flight(flight_number: int, aircraft_id: int, origin: str, destination: str, departure_time: datetime, flight_status: str = "Active") -> tuple[bool, str]:  # Creates a new flight with validations (route exists, Large for >6h, unique number)
        origin = (origin or "").strip()
        destination = (destination or "").strip()
        flight_status = (flight_status or "Active").strip() or "Active"
        if not origin or not destination:
            return False, "חובה לבחור שדה מקור ושדה יעד"
        if not isinstance(departure_time, datetime):
            return False, "תאריך/שעת המראה לא תקין"
        length = Flight.get_route_length(origin, destination)
        if not length:
            return False, "לא ניתן להוסיף טיסה לנתיב שלא קיים. קודם הוסף קו טיסה (FlightLength)."
        duration_sec = Flight.get_route_duration_seconds(origin, destination)
        size = Flight.get_aircraft_size(int(aircraft_id))
        if duration_sec > 6 * 3600 and size != "large":
            return False, "טיסה מעל 6 שעות חייבת להיות עם מטוס Large"
        if Flight.flight_number_exists(int(flight_number)):
            return False, "מספר טיסה כבר קיים במערכת"
        with DB.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO Flight (flight_number, aircraft_id, origin, destination, departure_time, flight_status)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (int(flight_number), int(aircraft_id), origin, destination, departure_time, flight_status))
        return True, "טיסה נוצרה בהצלחה"

    @staticmethod
    def can_manager_cancel(flight_number: int) -> bool:  # Returns True if manager is allowed to cancel (>=72h before departure and not final status)
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT departure_time, flight_status FROM Flight WHERE flight_number = %s", (int(flight_number),))
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
    def cancel_flight(flight_number: int) -> tuple[bool, str]:  # Cancels a flight (>=72h) and updates all related bookings as canceled by airline
        if not flight_number:
            return False, "מספר טיסה חסר"
        flight_number = int(flight_number)
        if not Flight.can_manager_cancel(flight_number):
            return False, "לא ניתן לבטל טיסה פחות מ-72 שעות לפני ההמראה"
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT flight_status FROM Flight WHERE flight_number = %s", (flight_number,))
            f = cursor.fetchone()
            if not f:
                return False, "הטיסה לא קיימת"
            current_status = (f.get("flight_status") or "").strip()
            if current_status == "Completed":
                return False, "לא ניתן לבטל טיסה שהושלמה"
            if current_status == "Canceled":
                return True, "הטיסה כבר בוטלה"
            cursor.execute("UPDATE Flight SET flight_status = 'Canceled' WHERE flight_number = %s", (flight_number,))
            cursor.execute("""
                UPDATE Booking
                SET price = 0,
                    booking_status = 'Canceled by Airline'
                WHERE flight_number = %s
            """, (flight_number,))
        return True, "הטיסה בוטלה וההזמנות עודכנו"

    @staticmethod
    def search_routes(origin: str = "", destination: str = ""):  # Searches routes in FlightLength with optional origin/destination filters
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
    def create_route(origin: str, destination: str, length_minutes: str) -> tuple[bool, str | None]:  # Creates a new route in FlightLength with basic validation
        origin = (origin or "").strip()
        destination = (destination or "").strip()
        length_minutes = (length_minutes or "").strip()
        if not origin or not destination or not length_minutes:
            return False, "יש למלא מקור, יעד ואורך טיסה"
        if origin == destination:
            return False, "מקור ויעד לא יכולים להיות זהים"
        parts = length_minutes.split(":")
        if len(parts) not in (2, 3):
            return False, "פורמט אורך טיסה לא תקין. השתמש HH:MM או HH:MM:SS"
        try:
            with DB.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO FlightLength (origin, destination, length_minutes)
                    VALUES (%s, %s, %s)
                """, (origin, destination, length_minutes))
            return True, None
        except Exception as e:
            msg = str(e)
            if "Duplicate" in msg or "1062" in msg:
                return False, "קו כזה כבר קיים (אותו מקור ואותו יעד)"
            return False, f"שגיאת DB: {msg}"

    @staticmethod
    def get_route_origins_distinct():  # Returns distinct origins from FlightLength (legacy dropdown helper)
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT origin FROM FlightLength ORDER BY origin")
            rows = cursor.fetchall() or []
        return [r["origin"] for r in rows]

    @staticmethod
    def get_route_destinations_distinct():  # Returns distinct destinations from FlightLength (legacy dropdown helper)
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT DISTINCT destination FROM FlightLength ORDER BY destination")
            rows = cursor.fetchall() or []
        return [r["destination"] for r in rows]

    @staticmethod
    def get_route_info(origin: str, destination: str):  # Returns route length_time and duration_sec for validations/preview
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
        return {"length_time": row.get("length_time"), "duration_sec": int(row.get("duration_sec") or 0)}

    @staticmethod
    def compute_arrival(dep_dt: datetime, origin: str, destination: str):  # Computes arrival datetime for preview using FlightLength
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT ADDTIME(%s, length_minutes) AS arrival_dt
                FROM FlightLength
                WHERE origin=%s AND destination=%s
            """, (dep_dt, origin, destination))
            row = cursor.fetchone() or {}
        return row.get("arrival_dt")

    @staticmethod
    def generate_next_flight_number() -> int:  # Generates the next flight_number using MAX+1
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(flight_number), 1000) AS m FROM Flight")
            row = cursor.fetchone() or {}
        return int(row.get("m") or 1000) + 1

    @staticmethod
    def list_available_aircrafts_for_route(origin: str, dep_dt: datetime, require_large: bool):  # Returns aircrafts available by last destination/time and optional Large requirement
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
                    (lf.aircraft_id IS NULL AND %s = 'TLV')
                    OR lf.last_destination = %s
                  )
            ORDER BY a.aircraft_id ASC
        """
        params = (dep_dt, dep_dt, origin, origin)
        with DB.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall() or []

    @staticmethod
    def get_pilots_by_ids(ids):  # Fetches pilot dicts (id + names) by list of ids for display
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
            return cursor.fetchall() or []

    @staticmethod
    def get_attendants_by_ids(ids):  # Fetches attendant dicts (id + names) by list of ids for display
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
            return cursor.fetchall() or []

    @staticmethod
    def get_all_airports_distinct():  # Returns all unique airports appearing in FlightLength (origin/destination union)
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT airport FROM (
                    SELECT origin AS airport FROM FlightLength
                    UNION
                    SELECT destination AS airport FROM FlightLength
                ) AS all_airports
                ORDER BY airport
            """)
            return [row["airport"] for row in (cursor.fetchall() or [])]

    @staticmethod
    def list_available_pilots_for_new_flight(origin: str, dep_dt: datetime, require_large: bool):  # Lists available pilots by last location and Large certification (deduped version)
        origin = (origin or "").strip()
        cert_clause = " AND p.big_aircraft_cert = 1 " if require_large else ""
        query = f"""
            SELECT
                p.id,
                p.first_name_he,
                p.last_name_he,
                p.big_aircraft_cert,
                lf.last_destination,
                lf.last_end_time
            FROM Pilot p
            LEFT JOIN (
                SELECT
                    t.crew_id,
                    SUBSTRING_INDEX(
                        GROUP_CONCAT(t.destination ORDER BY t.end_time DESC SEPARATOR ','), ',', 1
                    ) AS last_destination,
                    MAX(t.end_time) AS last_end_time
                FROM (
                    SELECT
                        pf.id AS crew_id,
                        f.destination,
                        COALESCE(
                            f.arrival_time,
                            ADDTIME(f.departure_time, fl.length_minutes)
                        ) AS end_time
                    FROM Pilots_on_Flights pf
                    JOIN Flight f
                      ON f.flight_number = pf.flight_number
                    LEFT JOIN FlightLength fl
                      ON fl.origin = f.origin AND fl.destination = f.destination
                    WHERE f.departure_time < %s
                ) t
                WHERE t.end_time <= %s
                GROUP BY t.crew_id
            ) lf ON lf.crew_id = p.id
            WHERE 1=1
              {cert_clause}
              AND (
                    (lf.crew_id IS NULL AND %s = 'TLV')
                    OR lf.last_destination = %s
                  )
            ORDER BY p.id ASC
        """
        params = (dep_dt, dep_dt, origin, origin)
        with DB.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall() or []

    @staticmethod
    def list_available_attendants_for_new_flight(origin: str, dep_dt: datetime, require_large: bool):  # Lists available attendants by last location and Large certification
        origin = (origin or "").strip()
        cert_clause = " AND fa.big_aircraft_cert = 1 " if require_large else ""
        query = f"""
            SELECT
                fa.id,
                fa.first_name_he,
                fa.last_name_he,
                fa.big_aircraft_cert,
                lf.last_destination,
                lf.last_end_time
            FROM FlightAttendant fa
            LEFT JOIN (
                SELECT
                    t.crew_id,
                    SUBSTRING_INDEX(
                        GROUP_CONCAT(t.destination ORDER BY t.end_time DESC SEPARATOR ','), ',', 1
                    ) AS last_destination,
                    MAX(t.end_time) AS last_end_time
                FROM (
                    SELECT
                        ff.id AS crew_id,
                        f.destination,
                        COALESCE(
                            f.arrival_time,
                            ADDTIME(f.departure_time, fl.length_minutes)
                        ) AS end_time
                    FROM FlightAttendants_on_Flights ff
                    JOIN Flight f
                      ON f.flight_number = ff.flight_number
                    LEFT JOIN FlightLength fl
                      ON fl.origin = f.origin AND fl.destination = f.destination
                    WHERE f.departure_time < %s
                ) t
                WHERE t.end_time <= %s
                GROUP BY t.crew_id
            ) lf ON lf.crew_id = fa.id
            WHERE 1=1
              {cert_clause}
              AND (
                    (lf.crew_id IS NULL AND %s = 'TLV')
                    OR lf.last_destination = %s
                  )
            ORDER BY fa.id ASC
        """
        params = (dep_dt, dep_dt, origin, origin)
        with DB.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall() or []