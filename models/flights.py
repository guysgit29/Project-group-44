class Aircraft:
    def __init__(self, aircraft_id, manufacturer, size):
        self.id = aircraft_id
        self.manufacturer = manufacturer
        self.size = size # 'Big' / 'Small'

class Flight:
    def __init__(self, flight_number, aircraft_id, origin, destination, departure, arrival, status):
        self.flight_number = flight_number
        self.aircraft_id = aircraft_id
        self.origin = origin
        self.destination = destination
        self.departure = departure
        self.arrival = arrival
        self.status = status

    @staticmethod
    def from_db(row):
        if not row: return None
        return Flight(
            row['flight_number'], row['aircraft_id'], row['origin'],
            row['destination'], row['departure_time'], row['arrival_time'], row['flight_status']
        )