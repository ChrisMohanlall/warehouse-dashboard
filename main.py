from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Text, DateTime
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from pydantic import BaseModel
from typing import List, Optional
import datetime

# --- DATABASE SETUP ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./fleet.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DATABASE MODELS ---
class DBLocation(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String)
    lat = Column(Float)
    lng = Column(Float)

class DBDriver(Base):
    __tablename__ = "drivers"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String)
    last_initial = Column(String)
    phone = Column(String)

class DBTruck(Base):
    __tablename__ = "trucks"
    id = Column(Integer, primary_key=True, index=True)
    truck_name = Column(String, unique=True, index=True)
    license_plate = Column(String)
    purpose = Column(String)
    current_driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=True)
    lat = Column(Float)
    lng = Column(Float)
    initial_photo_url = Column(String, nullable=True)
    general_notes = Column(Text, nullable=True)
    resource_excel_url = Column(String, nullable=True)
    start_fuel = Column(Float) 

class DBTripLog(Base):
    __tablename__ = "trip_logs"
    id = Column(Integer, primary_key=True, index=True)
    truck_id = Column(Integer, ForeignKey("trucks.id"))
    driver_id = Column(Integer, ForeignKey("drivers.id"))
    current_trip_end_km = Column(Float)
    end_fuel = Column(Float)
    damage_notes = Column(Text)
    damage_pic_url = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class DBFuelLog(Base):
    __tablename__ = "fuel_logs"
    id = Column(Integer, primary_key=True, index=True)
    truck_id = Column(Integer, ForeignKey("trucks.id"))
    driver_id = Column(Integer, ForeignKey("drivers.id"))
    km_at_fuel_up = Column(Float)
    receipt_url = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class DBActivityLog(Base):
    __tablename__ = "activity_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    action = Column(String)
    details = Column(Text)

Base.metadata.create_all(bind=engine)

# --- HELPER FUNCTIONS ---
def log_activity(db: Session, action: str, details: str):
    new_log = DBActivityLog(action=action, details=details)
    db.add(new_log)
    db.commit()

# --- FASTAPI SETUP & SCHEMAS ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

class DriverCreate(BaseModel): first_name: str; last_initial: str; phone: str
class LocationCreate(BaseModel): name: str; type: str; lat: float; lng: float
class TruckCreate(BaseModel): truck_name: str; license_plate: str; purpose: str; location_id: int; start_fuel: float; initial_photo_url: str = ""; general_notes: str = ""; resource_excel_url: str = ""
class TruckUpdate(BaseModel): license_plate: str; purpose: str; start_fuel: float; general_notes: str = ""; resource_excel_url: str = ""
class FuelLogCreate(BaseModel): truck_id: int; driver_id: int; km_at_fuel_up: float; receipt_url: str

class TripLogCreate(BaseModel): 
    truck_id: int; 
    driver_id: int; 
    destination_location_id: int; 
    current_trip_end_km: float; 
    end_fuel: float; 
    damage_notes: str; 
    damage_pic_url: str = ""
    exact_lat: Optional[float] = None
    exact_lng: Optional[float] = None

# --- API ENDPOINTS ---

# DRIVERS
@app.get("/drivers/")
def get_drivers(db: Session = Depends(get_db)): return db.query(DBDriver).all()

@app.post("/drivers/")
def create_driver(driver: DriverCreate, db: Session = Depends(get_db)):
    new_driver = DBDriver(**driver.model_dump())
    db.add(new_driver)
    db.commit()
    log_activity(db, "Add Driver", f"Added driver: {driver.first_name} {driver.last_initial}.")
    return {"message": "Driver added successfully!"}

@app.delete("/drivers/{driver_id}")
def delete_driver(driver_id: int, db: Session = Depends(get_db)):
    driver = db.query(DBDriver).filter(DBDriver.id == driver_id).first()
    log_activity(db, "Remove Driver", f"Removed driver: {driver.first_name} {driver.last_initial}.")
    db.delete(driver); db.commit()
    return {"message": "Driver removed."}

# LOCATIONS
@app.get("/locations/")
def get_locations(db: Session = Depends(get_db)): return db.query(DBLocation).all()

@app.post("/locations/")
def create_location(loc: LocationCreate, db: Session = Depends(get_db)):
    db.add(DBLocation(**loc.model_dump())); db.commit()
    log_activity(db, "Add Location", f"Added location: {loc.name}.")
    return {"message": "Location added!"}

@app.delete("/locations/{loc_id}")
def delete_location(loc_id: int, db: Session = Depends(get_db)):
    loc = db.query(DBLocation).filter(DBLocation.id == loc_id).first()
    log_activity(db, "Remove Location", f"Removed location: {loc.name}.")
    db.delete(loc); db.commit()
    return {"message": "Location removed."}

# TRUCKS
@app.get("/trucks/")
def get_trucks(db: Session = Depends(get_db)): 
    trucks = db.query(DBTruck).all()
    for t in trucks:
        if t.current_driver_id:
            driver = db.query(DBDriver).filter(DBDriver.id == t.current_driver_id).first()
            t.current_driver_name = f"{driver.first_name} {driver.last_initial}." if driver else "Unknown"
        else:
            t.current_driver_name = "None"
    return trucks

@app.post("/trucks/")
def create_truck(truck: TruckCreate, db: Session = Depends(get_db)):
    loc = db.query(DBLocation).filter(DBLocation.id == truck.location_id).first()
    new_truck = DBTruck(truck_name=truck.truck_name, license_plate=truck.license_plate, purpose=truck.purpose, lat=loc.lat, lng=loc.lng, start_fuel=truck.start_fuel, initial_photo_url=truck.initial_photo_url, general_notes=truck.general_notes, resource_excel_url=truck.resource_excel_url)
    db.add(new_truck); db.commit()
    log_activity(db, "Intake Truck", f"Added new truck: {truck.truck_name} ({truck.license_plate}).")
    return {"message": "Truck added!"}

@app.put("/trucks/{truck_id}")
def update_truck(truck_id: int, truck_update: TruckUpdate, db: Session = Depends(get_db)):
    truck = db.query(DBTruck).filter(DBTruck.id == truck_id).first()
    truck.license_plate = truck_update.license_plate
    truck.purpose = truck_update.purpose
    truck.start_fuel = truck_update.start_fuel
    truck.general_notes = truck_update.general_notes
    truck.resource_excel_url = truck_update.resource_excel_url
    log_activity(db, "Update Truck", f"Repurposed truck: {truck.truck_name}. New plate: {truck.license_plate}.")
    db.commit()
    return {"message": "Truck updated!"}

@app.delete("/trucks/{truck_id}")
def delete_truck(truck_id: int, db: Session = Depends(get_db)):
    truck = db.query(DBTruck).filter(DBTruck.id == truck_id).first()
    log_activity(db, "Remove Truck", f"Removed truck: {truck.truck_name}.")
    db.delete(truck); db.commit()
    return {"message": "Truck removed."}

# DRIVER ACTIONS
@app.post("/trip-logs/")
def create_trip_log(log: TripLogCreate, db: Session = Depends(get_db)):
    log_data = log.model_dump(exclude={"exact_lat", "exact_lng"})
    db.add(DBTripLog(**log_data))

    truck = db.query(DBTruck).filter(DBTruck.id == log.truck_id).first()
    loc = db.query(DBLocation).filter(DBLocation.id == log.destination_location_id).first()
    
    if log.exact_lat is not None and log.exact_lng is not None:
        truck.lat = log.exact_lat
        truck.lng = log.exact_lng
    else:
        truck.lat = loc.lat
        truck.lng = loc.lng
        
    truck.current_driver_id = log.driver_id
    
    log_activity(db, "Trip Log", f"Truck {truck.truck_name} parked near {loc.name}.")
    db.commit()
    return {"message": "Trip logged and exact location updated!"}

@app.post("/fuel-logs/")
def create_fuel_log(log: FuelLogCreate, db: Session = Depends(get_db)):
    db.add(DBFuelLog(**log.model_dump()))
    truck = db.query(DBTruck).filter(DBTruck.id == log.truck_id).first()
    driver = db.query(DBDriver).filter(DBDriver.id == log.driver_id).first()
    log_activity(db, "Fuel Up", f"{driver.first_name} fueled up {truck.truck_name} at {log.km_at_fuel_up} KM.")
    db.commit()
    return {"message": "Fuel log saved!"}

# ACTIVITY LOGS
@app.get("/activity-logs/")
def get_activity_logs(db: Session = Depends(get_db)):
    return db.query(DBActivityLog).order_by(DBActivityLog.timestamp.desc()).all()