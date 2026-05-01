import os
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Text, DateTime
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from pydantic import BaseModel
from typing import List, Optional
import datetime
load_dotenv()

# --- DATABASE SETUP ---
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fleet.db") 

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DATABASE MODELS ---
class DBSetting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True, index=True)
    value = Column(String)

class DBLocation(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String)
    description = Column(Text, nullable=True) 
    lat = Column(Float, nullable=True) 
    lng = Column(Float, nullable=True)
    icon_url = Column(String, nullable=True)

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
    status = Column(String, default="Parked") 
    current_driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=True)
    current_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True) 
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    initial_photo_url = Column(String, nullable=True)
    general_notes = Column(Text, nullable=True)
    resource_excel_url = Column(String, nullable=True)
    start_fuel = Column(Float) 
    icon_url = Column(String, nullable=True)

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
    user = Column(String, default="Admin") 
    action = Column(String)
    details = Column(Text)

Base.metadata.create_all(bind=engine)

# Seed initial settings if blank
db_init = SessionLocal()
if not db_init.query(DBSetting).first():
    db_init.add(DBSetting(key="race_name", value="CRS New Event"))
    db_init.add(DBSetting(key="icons", value=json.dumps(DEFAULT_ICONS)))
    db_init.commit()
db_init.close()

# --- DEFAULT SETTINGS ---
# Paste your permanent icon URLs here! You can add as many as you want.
DEFAULT_ICONS = [
    {"name": "Standard Teardrop", "url": ""},
    {"name": "CRS Banner Placeholder", "url": "https://github.com/ChrisMohanlall/warehouse-dashboard/blob/main/icons/crsbanner.png?raw=true"}
]

# --- HELPER FUNCTIONS ---
def log_activity(db: Session, user: str, action: str, details: str):
    db.add(DBActivityLog(user=user, action=action, details=details))
    db.commit()

# --- FASTAPI SETUP & SCHEMAS ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

class SettingUpdate(BaseModel): value: str
class SettingListUpdate(BaseModel): items: list
class DriverCreate(BaseModel): first_name: str; last_initial: str; phone: str
class LocationCreate(BaseModel): name: str; type: str; description: Optional[str] = ""; lat: Optional[float] = None; lng: Optional[float] = None; icon_url: Optional[str] = ""; user: str = "Admin"
class LocationUpdate(BaseModel): name: str; type: str; lat: Optional[float] = None; lng: Optional[float] = None; icon_url: Optional[str] = ""
class TruckCreate(BaseModel): truck_name: str; license_plate: str; purpose: str; location_id: int; start_fuel: float; status: str = "Parked"; initial_photo_url: str = ""; general_notes: str = ""; resource_excel_url: str = ""; icon_url: Optional[str] = ""
class TruckUpdate(BaseModel): license_plate: str; purpose: str; start_fuel: float; status: str; general_notes: str = ""; resource_excel_url: str = ""; icon_url: Optional[str] = ""
class FuelLogCreate(BaseModel): truck_id: int; driver_id: int; km_at_fuel_up: float; receipt_url: str
class TripLogCreate(BaseModel): truck_id: int; driver_id: int; destination_location_id: int; current_trip_end_km: float; end_fuel: float; damage_notes: str; damage_pic_url: str = ""

# --- API ENDPOINTS ---

@app.get("/")
def root(): return {"message": "CRS Dashboard API is live!"}

@app.get("/keep-awake/")
def keep_awake(db: Session = Depends(get_db)):
    db.query(DBLocation).first()
    return {"status": "Awake"}

@app.get("/config/")
def get_config(): return {"mapbox_token": os.getenv("MAPBOX_API_KEY", "")}

@app.get("/settings/{key}")
def get_setting(key: str, db: Session = Depends(get_db)):
    setting = db.query(DBSetting).filter(DBSetting.key == key).first()
    return {"value": setting.value if setting else "CRS Event"}

@app.put("/settings/{key}")
def update_setting(key: str, setting_update: SettingUpdate, db: Session = Depends(get_db)):
    setting = db.query(DBSetting).filter(DBSetting.key == key).first()
    if not setting: db.add(DBSetting(key=key, value=setting_update.value))
    else: setting.value = setting_update.value
    log_activity(db, "Admin", "Update Settings", f"Changed {key} to {setting_update.value}.")
    db.commit()
    return {"message": "Setting updated!"}

@app.get("/settings/list/{key}")
def get_setting_list(key: str, db: Session = Depends(get_db)):
    setting = db.query(DBSetting).filter(DBSetting.key == key).first()
    if setting and setting.value:
        try: return {"items": json.loads(setting.value)}
        except json.JSONDecodeError: return {"items": []}
    return {"items": []}

@app.put("/settings/list/{key}")
def update_setting_list(key: str, list_update: SettingListUpdate, db: Session = Depends(get_db)):
    setting = db.query(DBSetting).filter(DBSetting.key == key).first()
    json_val = json.dumps(list_update.items)
    if not setting: db.add(DBSetting(key=key, value=json_val))
    else: setting.value = json_val
    log_activity(db, "Admin", "Update Settings", f"Updated list for {key}.")
    db.commit()
    return {"message": "List updated!"}

@app.post("/wipe/")
def factory_reset():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    new_db = SessionLocal()
    new_db.add(DBSetting(key="race_name", value="CRS New Event"))
    new_db.add(DBSetting(key="icons", value=json.dumps(DEFAULT_ICONS)))
    log_activity(new_db, "System", "Factory Reset", "Database was completely wiped.")
    new_db.commit()
    new_db.close()
    return {"message": "Factory Reset Complete"}

@app.get("/drivers/")
def get_drivers(db: Session = Depends(get_db)): return db.query(DBDriver).all()

@app.post("/drivers/")
def create_driver(driver: DriverCreate, db: Session = Depends(get_db)):
    db.add(DBDriver(**driver.model_dump()))
    log_activity(db, "Admin", "Add Driver", f"Added driver: {driver.first_name} {driver.last_initial}.")
    db.commit()
    return {"message": "Driver added successfully!"}

@app.delete("/drivers/{driver_id}")
def delete_driver(driver_id: int, db: Session = Depends(get_db)):
    driver = db.query(DBDriver).filter(DBDriver.id == driver_id).first()
    log_activity(db, "Admin", "Remove Driver", f"Removed driver: {driver.first_name} {driver.last_initial}.")
    db.delete(driver); db.commit()
    return {"message": "Driver removed."}

@app.get("/locations/")
def get_locations(db: Session = Depends(get_db)): return db.query(DBLocation).all()

@app.post("/locations/")
def create_location(loc: LocationCreate, db: Session = Depends(get_db)):
    db.add(DBLocation(**loc.model_dump(exclude={"user"})))
    log_activity(db, loc.user, "Add Location", f"Added location: {loc.name} - {loc.type}.")
    db.commit()
    return {"message": "Location added!"}

@app.put("/locations/{loc_id}")
def update_location(loc_id: int, update_data: LocationUpdate, db: Session = Depends(get_db)):
    loc = db.query(DBLocation).filter(DBLocation.id == loc_id).first()
    loc.name = update_data.name
    loc.type = update_data.type
    loc.lat = update_data.lat
    loc.lng = update_data.lng
    loc.icon_url = update_data.icon_url
    log_activity(db, "Admin", "Edit Location", f"Updated location: {loc.name} - {loc.type}.")
    
    if update_data.lat is not None and update_data.lng is not None:
        trucks = db.query(DBTruck).filter(DBTruck.current_location_id == loc.id).all()
        for t in trucks: 
            t.lat = update_data.lat
            t.lng = update_data.lng
            
    db.commit()
    return {"message": "Location updated!"}

@app.delete("/locations/{loc_id}")
def delete_location(loc_id: int, db: Session = Depends(get_db)):
    loc = db.query(DBLocation).filter(DBLocation.id == loc_id).first()
    log_activity(db, "Admin", "Remove Location", f"Removed location: {loc.name} - {loc.type}.")
    db.delete(loc); db.commit()
    return {"message": "Location removed."}

@app.get("/trucks/")
def get_trucks(db: Session = Depends(get_db)): 
    trucks = db.query(DBTruck).all()
    drivers_dict = {d.id: f"{d.first_name} {d.last_initial}." for d in db.query(DBDriver).all()}
    locations_dict = {l.id: l for l in db.query(DBLocation).all()}

    for t in trucks:
        t.current_driver_name = drivers_dict.get(t.current_driver_id, "Unknown")
        loc = locations_dict.get(t.current_location_id)
        t.current_location_name = f"{loc.name} - {loc.type}" if loc else "Unknown"
        t.is_location_undefined = True if (loc and loc.lat is None) else False
    return trucks

@app.post("/trucks/")
def create_truck(truck: TruckCreate, db: Session = Depends(get_db)):
    loc = db.query(DBLocation).filter(DBLocation.id == truck.location_id).first()
    db.add(DBTruck(truck_name=truck.truck_name, license_plate=truck.license_plate, purpose=truck.purpose, status=truck.status, lat=loc.lat, lng=loc.lng, current_location_id=loc.id, start_fuel=truck.start_fuel, initial_photo_url=truck.initial_photo_url, general_notes=truck.general_notes, resource_excel_url=truck.resource_excel_url, icon_url=truck.icon_url))
    log_activity(db, "Admin", "Intake Truck", f"Added new truck: {truck.truck_name}.")
    db.commit()
    return {"message": "Truck added!"}

@app.put("/trucks/{truck_id}")
def update_truck(truck_id: int, truck_update: TruckUpdate, db: Session = Depends(get_db)):
    truck = db.query(DBTruck).filter(DBTruck.id == truck_id).first()
    truck.license_plate = truck_update.license_plate
    truck.purpose = truck_update.purpose
    truck.start_fuel = truck_update.start_fuel
    truck.status = truck_update.status
    truck.general_notes = truck_update.general_notes
    truck.resource_excel_url = truck_update.resource_excel_url
    truck.icon_url = truck_update.icon_url
    log_activity(db, "Admin", "Update Truck", f"Updated truck: {truck.truck_name}.")
    db.commit()
    return {"message": "Truck updated!"}

@app.delete("/trucks/{truck_id}")
def delete_truck(truck_id: int, db: Session = Depends(get_db)):
    truck = db.query(DBTruck).filter(DBTruck.id == truck_id).first()
    log_activity(db, "Admin", "Remove Truck", f"Removed truck: {truck.truck_name}.")
    db.delete(truck); db.commit()
    return {"message": "Truck removed."}

@app.post("/trip-logs/")
def create_trip_log(log: TripLogCreate, db: Session = Depends(get_db)):
    db.add(DBTripLog(**log.model_dump()))
    truck = db.query(DBTruck).filter(DBTruck.id == log.truck_id).first()
    loc = db.query(DBLocation).filter(DBLocation.id == log.destination_location_id).first()
    driver = db.query(DBDriver).filter(DBDriver.id == log.driver_id).first()
    
    truck.lat = loc.lat; truck.lng = loc.lng
    truck.current_location_id = loc.id; truck.current_driver_id = driver.id
    truck.status = "Parked" 
    
    log_activity(db, f"{driver.first_name} {driver.last_initial}.", "Trip Log", f"Truck {truck.truck_name} parked at {loc.name} - {loc.type}.")
    db.commit()
    return {"message": "Trip logged!"}

@app.post("/fuel-logs/")
def create_fuel_log(log: FuelLogCreate, db: Session = Depends(get_db)):
    db.add(DBFuelLog(**log.model_dump()))
    truck = db.query(DBTruck).filter(DBTruck.id == log.truck_id).first()
    driver = db.query(DBDriver).filter(DBDriver.id == log.driver_id).first()
    log_activity(db, f"{driver.first_name} {driver.last_initial}.", "Fuel Up", f"Fueled up {truck.truck_name} at {log.km_at_fuel_up} KM.")
    db.commit()
    return {"message": "Fuel log saved!"}

@app.get("/activity-logs/")
def get_activity_logs(db: Session = Depends(get_db)):
    return db.query(DBActivityLog).order_by(DBActivityLog.timestamp.desc()).all()
