DROP DATABASE IF EXISTS flytau;
CREATE DATABASE flytau;
USE flytau;

-- =================================================
-- Manager / Pilot / FlightAttendant
-- =================================================
CREATE TABLE Manager (
    id INT NOT NULL,
    first_name_he VARCHAR(50),
    last_name_he VARCHAR(50),
    start_date DATE,
    city VARCHAR(100),
    street VARCHAR(100),
    phone_num VARCHAR(100),
    house_number INT,
    password VARCHAR(20),
    PRIMARY KEY (id)
);

CREATE TABLE Pilot (
    id INT NOT NULL,
    first_name_he VARCHAR(50),
    last_name_he VARCHAR(50),
    start_date DATE,
    city VARCHAR(100),
    street VARCHAR(100),
    house_number INT,
    phone_num VARCHAR(100),
    big_aircraft_cert TINYINT,
    PRIMARY KEY (id)
);

CREATE TABLE FlightAttendant (
    id INT NOT NULL,
    first_name_he VARCHAR(50),
    last_name_he VARCHAR(50),
    start_date DATE,
    city VARCHAR(100),
    street VARCHAR(100),
    house_number INT,
    phone_num VARCHAR(100),
    big_aircraft_cert TINYINT,
    PRIMARY KEY (id)
);

-- =================================================
-- Aircraft / Class / Seat
-- =================================================
CREATE TABLE Aircraft (
    aircraft_id INT NOT NULL,
    manufacturer VARCHAR(100),
    purchase_date DATE,
    aircraft_size VARCHAR(50), -- 'Large' / 'Small'
    PRIMARY KEY (aircraft_id)
);

CREATE TABLE Class (
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    total_rows INT,
    total_columns INT,
    PRIMARY KEY (aircraft_id, class_type),
    FOREIGN KEY (aircraft_id) REFERENCES Aircraft(aircraft_id)
);

CREATE TABLE Seat (
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    row_num INT NOT NULL,
    column_number INT NOT NULL,
    PRIMARY KEY (aircraft_id, class_type, row_num, column_number),
    FOREIGN KEY (aircraft_id, class_type)
        REFERENCES Class(aircraft_id, class_type)
);

-- =================================================
-- Users
-- =================================================
CREATE TABLE GuestUser (
    email VARCHAR(255) NOT NULL,
    first_name_en VARCHAR(50),
    last_name_en VARCHAR(50),
    PRIMARY KEY (email)
);

CREATE TABLE GuestPhone (
    email VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    PRIMARY KEY (email, phone_number),
    FOREIGN KEY (email) REFERENCES GuestUser(email)
);

CREATE TABLE RegisteredUser (
    email VARCHAR(255) NOT NULL,
    first_name_en VARCHAR(50),
    last_name_en VARCHAR(50),
    birth_date DATE,
    registration_date DATE,
    passport_number VARCHAR(20),
    password VARCHAR(20),
    PRIMARY KEY (email)
);

CREATE TABLE RegisteredPhone (
    email VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    PRIMARY KEY (email, phone_number),
    FOREIGN KEY (email) REFERENCES RegisteredUser(email)
);

-- =================================================
-- FlightLength / Flight (+ trigger arrival time)
-- =================================================
CREATE TABLE FlightLength (
    origin VARCHAR(100) NOT NULL,
    destination VARCHAR(100) NOT NULL,
    length_minutes TIME,
    PRIMARY KEY (origin, destination)
);

CREATE TABLE Flight (
    flight_number INT NOT NULL,
    aircraft_id INT,
    origin VARCHAR(100),
    destination VARCHAR(100),
    departure_time DATETIME,
    arrival_time DATETIME DEFAULT NULL,
    flight_status VARCHAR(50),
    PRIMARY KEY (flight_number),
    FOREIGN KEY (aircraft_id) REFERENCES Aircraft(aircraft_id)
);

DELIMITER //
CREATE TRIGGER before_flight_insert
BEFORE INSERT ON Flight
FOR EACH ROW
BEGIN
    DECLARE duration_val TIME;

    SELECT length_minutes INTO duration_val
    FROM FlightLength
    WHERE origin = NEW.origin AND destination = NEW.destination;

    IF duration_val IS NOT NULL THEN
        SET NEW.arrival_time = ADDTIME(NEW.departure_time, duration_val);
    END IF;
END;
//
DELIMITER ;

-- =================================================
-- Booking / Ticket
-- =================================================
CREATE TABLE Booking (
    booking_id VARCHAR(6) NOT NULL,
    registered_email VARCHAR(255) NULL,
    guest_email VARCHAR(255),
    flight_number INT,
    price DECIMAL(10,2),
    booking_date DATE,
    booking_status VARCHAR(50),
    PRIMARY KEY (booking_id),
    FOREIGN KEY (registered_email) REFERENCES RegisteredUser(email),
    FOREIGN KEY (guest_email) REFERENCES GuestUser(email),
    FOREIGN KEY (flight_number) REFERENCES Flight(flight_number)
);

CREATE TABLE Ticket (
    booking_id VARCHAR(6) NOT NULL,
    flight_number INT NOT NULL,
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    row_num INT NOT NULL,
    column_number INT NOT NULL,
    PRIMARY KEY (
        booking_id, flight_number, aircraft_id, class_type, row_num, column_number
    ),
    FOREIGN KEY (booking_id) REFERENCES Booking(booking_id),
    FOREIGN KEY (flight_number) REFERENCES Flight(flight_number),
    FOREIGN KEY (aircraft_id, class_type, row_num, column_number)
        REFERENCES Seat(aircraft_id, class_type, row_num, column_number)
);

-- =================================================
-- Crew assignment tables
-- =================================================
CREATE TABLE FlightAttendants_on_Flights (
    id INT NOT NULL,
    flight_number INT NOT NULL,
    PRIMARY KEY (id, flight_number),
    FOREIGN KEY (id) REFERENCES FlightAttendant(id),
    FOREIGN KEY (flight_number) REFERENCES Flight(flight_number)
);

CREATE TABLE Pilots_on_Flights (
    id INT NOT NULL,
    flight_number INT NOT NULL,
    PRIMARY KEY (id, flight_number),
    FOREIGN KEY (id) REFERENCES Pilot(id),
    FOREIGN KEY (flight_number) REFERENCES Flight(flight_number)
);

-- =================================================
-- Classes_on_Flights / Seats_on_Flights / Seats_in_Booking
-- =================================================
CREATE TABLE Classes_on_Flights (
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    flight_number INT NOT NULL,
    class_price DECIMAL(10,2),
    PRIMARY KEY (aircraft_id, class_type, flight_number),
    FOREIGN KEY (aircraft_id, class_type)
        REFERENCES Class(aircraft_id, class_type),
    FOREIGN KEY (flight_number)
        REFERENCES Flight(flight_number)
);

CREATE TABLE Seats_on_Flights (
    aircraft_id INT NOT NULL,
    class_type VARCHAR(50) NOT NULL,
    row_num INT NOT NULL,
    column_number INT NOT NULL,
    flight_number INT NOT NULL,
    available TINYINT,
    PRIMARY KEY (aircraft_id, class_type, row_num, column_number, flight_number),
    FOREIGN KEY (aircraft_id, class_type, row_num, column_number)
        REFERENCES Seat(aircraft_id, class_type, row_num, column_number),
    FOREIGN KEY (flight_number)
        REFERENCES Flight(flight_number)
);

DROP TRIGGER IF EXISTS trg_flight_after_insert_seed_seats;
DELIMITER $$

CREATE TRIGGER trg_flight_after_insert_seed_seats
AFTER INSERT ON Flight
FOR EACH ROW
BEGIN
  INSERT IGNORE INTO Seats_on_Flights (
    aircraft_id, class_type, row_num, column_number, flight_number, available
  )
  SELECT
    s.aircraft_id, s.class_type, s.row_num, s.column_number,
    NEW.flight_number,
    1
  FROM Seat s
  WHERE s.aircraft_id = NEW.aircraft_id;
END$$

DELIMITER ;

DROP TRIGGER IF EXISTS trg_ticket_ai_mark_unavailable;
DELIMITER $$

CREATE TRIGGER trg_ticket_ai_mark_unavailable
AFTER INSERT ON Ticket
FOR EACH ROW
BEGIN
  UPDATE Seats_on_Flights sof
  SET sof.available = 0
  WHERE sof.aircraft_id   = NEW.aircraft_id
    AND sof.class_type    = NEW.class_type
    AND sof.row_num       = NEW.row_num
    AND sof.column_number = NEW.column_number
    AND sof.flight_number = NEW.flight_number;
END$$

DELIMITER ;