import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

OUTPUT_DIR = "converted_tcx"
os.makedirs(OUTPUT_DIR, exist_ok=True)

EXPORT_PATH = None
possible_paths = [
    "export.xml",
    "apple_health_export/export.xml",
    "apple_health_export/apple_health_export/export.xml"
]

for p in possible_paths:
    if os.path.exists(p):
        EXPORT_PATH = p
        break

if not EXPORT_PATH:
    for root_dir, _, files in os.walk("."):
        if "export.xml" in files:
            EXPORT_PATH = os.path.join(root_dir, "export.xml")
            break

if not EXPORT_PATH:
    raise FileNotFoundError("Could not locate export.xml. Ensure export.xml is unzipped inside this folder.")

print(f"Found export file at: {EXPORT_PATH}")
print("Streaming XML and generating Strava-compatible TCX files...")

ACTIVITY_MAP = {
    # Cardio & Running / Cycling
    "HKWorkoutActivityTypeRunning": ("Run", "Running", None),
    "HKWorkoutActivityTypeCycling": ("Ride", "Biking", None),
    "HKWorkoutActivityTypeWalking": ("Walk", "Running", None),
    "HKWorkoutActivityTypeHiking": ("Hike", "Running", None),
    
    # Swims mapped specifically for Strava auto-categorization
    "HKWorkoutActivityTypeSwimming": ("Swim", "Other", "LapSwimming"),
    "HKWorkoutActivityTypePoolSwimming": ("PoolSwim", "Other", "LapSwimming"),
    "HKWorkoutActivityTypeOpenWaterSwimming": ("OpenWaterSwim", "Other", "OpenWaterSwimming"),
    
    # Gym & Fitness Equipment
    "HKWorkoutActivityTypeElliptical": ("Elliptical", "Other", None),
    "HKWorkoutActivityTypeRower": ("Rowing", "Other", "Rowing"),
    "HKWorkoutActivityTypeStairClimbing": ("StairStepper", "Other", None),
    "HKWorkoutActivityTypeStepTraining": ("StepTraining", "Other", None),
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": ("HIIT", "Other", None),
    
    # Strength & Conditioning
    "HKWorkoutActivityTypeTraditionalStrengthTraining": ("StrengthTraining", "Other", None),
    "HKWorkoutActivityTypeFunctionalStrengthTraining": ("FunctionalStrength", "Other", None),
    "HKWorkoutActivityTypeCoreTraining": ("CoreTraining", "Other", None),
    "HKWorkoutActivityTypeCrossTraining": ("CrossTraining", "Other", None),
    
    # Mind & Body
    "HKWorkoutActivityTypeYoga": ("Yoga", "Other", None),
    "HKWorkoutActivityTypePilates": ("Pilates", "Other", None),
    "HKWorkoutActivityTypeFlexibility": ("Stretching", "Other", None),
    "HKWorkoutActivityTypeMindAndBody": ("MindAndBody", "Other", None),
    "HKWorkoutActivityTypeBarre": ("Barre", "Other", None),

    # Sports
    "HKWorkoutActivityTypeSoccer": ("Soccer", "Other", None),
    "HKWorkoutActivityTypeBasketball": ("Basketball", "Other", None),
    "HKWorkoutActivityTypeTennis": ("Tennis", "Other", None),
    "HKWorkoutActivityTypePickleball": ("Pickleball", "Other", None),
    "HKWorkoutActivityTypeVolleyball": ("Volleyball", "Other", None),
    "HKWorkoutActivityTypeGolf": ("Golf", "Other", None),

    # Other
    "HKWorkoutActivityTypeCooldown": ("Cooldown", "Other", None),
    "HKWorkoutActivityTypePlay": ("Play", "Other", None),
}

count = 0

context = ET.iterparse(EXPORT_PATH, events=("end",))
for event, elem in context:
    if elem.tag == "Workout":
        count += 1
        raw_type = elem.attrib.get("workoutActivityType", "")
        start_str = elem.attrib.get("startDate", "")
        duration = elem.attrib.get("duration", "0")
        
        try:
            start_dt = datetime.strptime(start_str[:-5].strip(), "%Y-%m-%d %H:%M:%S")
            start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            elem.clear()
            continue

        try:
            duration_sec = float(duration) * 60
        except ValueError:
            duration_sec = 0

        end_dt = start_dt + timedelta(seconds=duration_sec)
        end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        calories = 0
        distance_meters = 0

        for stats in elem.findall("WorkoutStatistics"):
            stat_type = stats.attrib.get("type", "")
            if "ActiveEnergyBurned" in stat_type:
                try:
                    calories = float(stats.attrib.get("sum", 0))
                except ValueError:
                    calories = 0
            elif "Distance" in stat_type:
                try:
                    unit = stats.attrib.get("unit", "")
                    val = float(stats.attrib.get("sum", 0))
                    if unit == "mi":
                        distance_meters = val * 1609.34
                    elif unit == "km":
                        distance_meters = val * 1000
                    elif unit in ["m", "yd"]:
                        distance_meters = val * 0.9144 if unit == "yd" else val
                    else:
                        distance_meters = val
                except ValueError:
                    distance_meters = 0

        explicit_indoor = False
        explicit_outdoor = False

        for meta in elem.findall("MetadataEntry"):
            key = meta.attrib.get("key", "").lower()
            val = str(meta.attrib.get("value", "")).lower()

            if "indoor" in key or "treadmill" in key or "fitnessplus" in key:
                if val in ["1", "true", "yes"]:
                    explicit_indoor = True
            elif "outdoor" in key or "gpx" in key or "location" in key:
                if val in ["1", "true", "yes"]:
                    explicit_outdoor = True

        has_route = False
        for child in elem:
            if "Route" in child.tag or "Location" in child.tag:
                has_route = True
                break

        label, tcx_sport, sub_sport = ACTIVITY_MAP.get(raw_type, ("Workout", "Other", None))

        if raw_type in [
            "HKWorkoutActivityTypeRunning",
            "HKWorkoutActivityTypeCycling",
            "HKWorkoutActivityTypeWalking",
            "HKWorkoutActivityTypeHiking"
        ]:
            if explicit_indoor:
                env_prefix = "Indoor"
            elif has_route or explicit_outdoor:
                env_prefix = "Outdoor"
            else:
                env_prefix = "Indoor"
            name_str = f"{env_prefix}_{label}"
        else:
            name_str = label

        # Inject Garmin SubSport extension for Swimming
        sub_sport_xml = ""
        if sub_sport:
            sub_sport_xml = f"""
        <Extensions>
          <UserExtension xmlns="http://www.garmin.com/xmlschemas/UserExtension/v1">
            <SubSport>{sub_sport}</SubSport>
          </UserExtension>
        </Extensions>"""

        tcx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase 
  xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd">
  <Activities>
    <Activity Sport="{tcx_sport}">
      <Id>{start_iso}</Id>
      <Lap StartTime="{start_iso}">
        <TotalTimeSeconds>{duration_sec}</TotalTimeSeconds>
        <DistanceMeters>{distance_meters}</DistanceMeters>
        <Calories>{int(calories)}</Calories>
        <Intensity>Active</Intensity>
        <TriggerMethod>Manual</TriggerMethod>
        <Track>
          <Trackpoint>
            <Time>{start_iso}</Time>
            <DistanceMeters>0</DistanceMeters>
          </Trackpoint>
          <Trackpoint>
            <Time>{end_iso}</Time>
            <DistanceMeters>{distance_meters}</DistanceMeters>
          </Trackpoint>
        </Track>{sub_sport_xml}
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>"""

        timestamp_str = start_dt.strftime('%Y%m%d_%H%M%S')
        file_name = os.path.join(OUTPUT_DIR, f"workout_{timestamp_str}_{name_str}.tcx")
        
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(tcx_content)
        
        elem.clear()

print(f"Done! Re-generated {count} TCX files in ./{OUTPUT_DIR}/")
