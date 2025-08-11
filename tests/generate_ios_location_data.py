#!/usr/bin/env python3
"""
Generate realistic iOS Core Location test data for Nashville, TN.
Creates a full day of location data with realistic movement patterns,
GPS drift, traffic simulation, and environmental effects.
"""

import json
import random
import math
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple, Optional
import uuid

class NashvilleLocationGenerator:
    def __init__(self):
        # Load Nashville locations and routes
        with open('nashville_locations.json', 'r') as f:
            self.data = json.load(f)

        self.locations = self.data['locations']
        self.routes = self.data['routes']
        self.traffic = self.data['traffic_patterns']
        self.movement = self.data['movement_profiles']

        # Device ID for the test data
        self.device_id = str(uuid.uuid4())

        # Schedule from TEST_DAY.md
        self.schedule = self._parse_schedule()

    def _parse_schedule(self) -> List[Dict]:
        """Parse the schedule from TEST_DAY.md into waypoints."""
        return [
            {"time": "07:23:14", "location": "home", "activity": "wake", "duration": 22},
            {"time": "07:45:32", "location": "shelby_bottoms_greenway", "activity": "dog_walk", "mode": "walking", "duration": 27},
            {"time": "08:12:27", "location": "home", "activity": "breakfast", "duration": 40},
            {"time": "08:52:09", "location": "crema_coffee", "activity": "coffee_work", "mode": "biking", "duration": 83},
            {"time": "10:15:21", "location": "the_gym_nashville", "activity": "workout", "mode": "driving", "duration": 75},
            {"time": "11:30:44", "location": "farmers_market", "activity": "shopping", "mode": "driving", "duration": 43},
            {"time": "12:14:07", "location": "home", "activity": "lunch", "mode": "driving", "duration": 80},
            {"time": "13:34:28", "location": "centennial_park", "activity": "pickleball", "mode": "driving", "duration": 71},
            {"time": "14:45:19", "location": "home", "activity": "dog_walk_2", "mode": "driving", "then": "walking", "duration": 47},
            {"time": "15:32:08", "location": "cvs_green_hills", "activity": "errand", "mode": "driving", "duration": 28},
            {"time": "16:00:33", "location": "home", "activity": "video_call", "mode": "driving", "duration": 45},
            {"time": "16:45:12", "location": "home", "activity": "text", "duration": 13},
            {"time": "16:58:42", "location": "shell_station", "activity": "gas", "mode": "driving", "duration": 4},
            {"time": "17:02:18", "location": "etch_restaurant", "activity": "dinner", "mode": "driving", "duration": 118},
            {"time": "19:00:42", "location": "home", "activity": "dog_walk_3", "mode": "driving", "then": "walking", "duration": 87},
            {"time": "20:28:03", "location": "patterson_house", "activity": "drinks", "mode": "driving", "duration": 79},
            {"time": "21:47:29", "location": "patterson_house", "activity": "quiz", "duration": 43},
            {"time": "22:30:15", "location": "home", "activity": "reading", "mode": "driving", "duration": 68},
            {"time": "23:38:21", "location": "home", "activity": "sleep", "duration": 0}
        ]

    def generate_day_data(self) -> Dict:
        """Generate a full day of location data."""
        data_points = []
        base_date = datetime(2025, 5, 3, 0, 0, 0, tzinfo=timezone.utc)  # Saturday

        for i, event in enumerate(self.schedule):
            # Parse event time
            time_parts = event['time'].split(':')
            event_time = base_date.replace(
                hour=int(time_parts[0]),
                minute=int(time_parts[1]),
                second=int(time_parts[2])
            )

            # Get location details
            location = self.locations[event['location']]

            # Handle transitions between events
            if i > 0 and 'mode' in event:
                prev_location = self.locations[self.schedule[i-1]['location']]

                # Generate movement data
                transition_points = self._generate_transition(
                    prev_location, location,
                    self.schedule[i-1], event,
                    event_time
                )
                data_points.extend(transition_points)

            # Generate stationary data for the activity duration
            if event['duration'] > 0:
                activity_points = self._generate_activity_data(
                    location, event, event_time, event['duration']
                )
                data_points.extend(activity_points)

        # Format as iOS location stream
        return {
            "stream_name": "ios_location",
            "device_id": self.device_id,
            "data": data_points
        }

    def _generate_transition(self, start_loc: Dict, end_loc: Dict,
                            start_event: Dict, end_event: Dict,
                            arrival_time: datetime) -> List[Dict]:
        """Generate location points for movement between two locations."""
        points = []
        mode = end_event.get('mode', 'driving')

        # Calculate distance and duration
        distance = self._calculate_distance(
            start_loc['lat'], start_loc['lng'],
            end_loc['lat'], end_loc['lng']
        )

        # Estimate travel time based on mode and traffic
        travel_time = self._estimate_travel_time(distance, mode, arrival_time.hour)

        # Start time is arrival minus travel time
        start_time = arrival_time - timedelta(minutes=travel_time)

        # Number of points (every 10 seconds)
        num_points = max(1, int(travel_time * 60 / 10))

        # Special handling for driving with parking
        if mode == 'driving':
            points.extend(self._generate_driving_route(
                start_loc, end_loc, start_time, num_points, arrival_time.hour
            ))
        elif mode == 'biking':
            points.extend(self._generate_biking_route(
                start_loc, end_loc, start_time, num_points
            ))
        elif mode == 'walking':
            points.extend(self._generate_walking_route(
                start_loc, end_loc, start_time, num_points
            ))

        return points

    def _generate_driving_route(self, start: Dict, end: Dict,
                               start_time: datetime, num_points: int,
                               hour: int) -> List[Dict]:
        """Generate driving route with traffic lights and realistic speeds."""
        points = []

        # Determine traffic level
        if 6 <= hour < 10:
            traffic_pattern = self.traffic['saturday_morning']
        elif 10 <= hour < 17:
            traffic_pattern = self.traffic['saturday_afternoon']
        else:
            traffic_pattern = self.traffic['saturday_evening']

        # Add parking search at destination
        parking_points = max(6, int(num_points * 0.1))  # 10% of time for parking
        driving_points = num_points - parking_points

        # Generate main driving route
        for i in range(driving_points):
            progress = i / max(1, driving_points - 1)
            timestamp = start_time + timedelta(seconds=i * 10)

            # Interpolate position
            lat = start['lat'] + (end['lat'] - start['lat']) * progress
            lng = start['lng'] + (end['lng'] - start['lng']) * progress

            # Add traffic stops (every 400-600m in city)
            if i > 0 and i % random.randint(20, 30) == 0:
                # Stop at traffic light
                speed = 0
                # Stay at same position for 30-90 seconds
                stop_duration = random.randint(3, 9)  # 3-9 data points
                for j in range(stop_duration):
                    if i + j < driving_points:
                        points.append(self._create_location_point(
                            lat, lng, start['altitude'], speed, timestamp,
                            accuracy_factor=1.0
                        ))
                        timestamp = timestamp + timedelta(seconds=10)
                i += stop_duration
            else:
                # Normal driving speed with variation
                base_speed = traffic_pattern['avg_speed_city_mph'] * 0.44704  # mph to m/s
                speed = max(0, base_speed + random.uniform(-3, 3))

                # Add slight position variation (lane changes, turns)
                lat += random.uniform(-0.00002, 0.00002)
                lng += random.uniform(-0.00002, 0.00002)

                points.append(self._create_location_point(
                    lat, lng, start['altitude'], speed, timestamp
                ))

        # Add parking search pattern near destination
        search_center_lat = end['lat']
        search_center_lng = end['lng']

        for i in range(parking_points):
            timestamp = start_time + timedelta(seconds=(driving_points + i) * 10)

            # Circle around destination
            angle = (i / parking_points) * 2 * math.pi
            radius = 0.001  # About 100m radius

            lat = search_center_lat + radius * math.cos(angle) * random.uniform(0.8, 1.2)
            lng = search_center_lng + radius * math.sin(angle) * random.uniform(0.8, 1.2)

            # Slow speed while searching
            speed = random.uniform(2, 5)  # 2-5 m/s

            points.append(self._create_location_point(
                lat, lng, end['altitude'], speed, timestamp
            ))

        return points

    def _generate_biking_route(self, start: Dict, end: Dict,
                              start_time: datetime, num_points: int) -> List[Dict]:
        """Generate biking route with appropriate speeds and stops."""
        points = []
        profile = self.movement['biking']

        for i in range(num_points):
            progress = i / max(1, num_points - 1)
            timestamp = start_time + timedelta(seconds=i * 10)

            # Interpolate position
            lat = start['lat'] + (end['lat'] - start['lat']) * progress
            lng = start['lng'] + (end['lng'] - start['lng']) * progress

            # Add path variation (not perfectly straight)
            lat += math.sin(progress * 10) * 0.0001
            lng += math.cos(progress * 10) * 0.0001

            # Speed variation
            if random.random() < profile['stop_probability']:
                speed = 0  # Stop at intersection
            else:
                speed = profile['base_speed_ms'] + random.uniform(
                    -profile['variation'], profile['variation']
                )
                speed = max(0, speed)

            # Altitude changes (Nashville has hills)
            altitude = start['altitude'] + (end['altitude'] - start['altitude']) * progress
            altitude += random.uniform(-2, 2)  # Small variations

            points.append(self._create_location_point(
                lat, lng, altitude, speed, timestamp
            ))

        return points

    def _generate_walking_route(self, start: Dict, end: Dict,
                               start_time: datetime, num_points: int) -> List[Dict]:
        """Generate walking route with realistic walking patterns."""
        points = []
        profile = self.movement['walking']

        for i in range(num_points):
            progress = i / max(1, num_points - 1)
            timestamp = start_time + timedelta(seconds=i * 10)

            # Interpolate position with slight meandering
            lat = start['lat'] + (end['lat'] - start['lat']) * progress
            lng = start['lng'] + (end['lng'] - start['lng']) * progress

            # Add natural walking path variation
            lat += random.uniform(-0.00003, 0.00003)
            lng += random.uniform(-0.00003, 0.00003)

            # Speed variation and stops
            if random.random() < profile['stop_probability']:
                speed = 0  # Stop to look at phone, wait for crossing, etc.
            else:
                speed = profile['base_speed_ms'] + random.uniform(
                    -profile['variation'], profile['variation']
                )
                speed = max(0, speed)

            points.append(self._create_location_point(
                lat, lng, start['altitude'], speed, timestamp
            ))

        return points

    def _generate_activity_data(self, location: Dict, event: Dict,
                               start_time: datetime, duration_min: int) -> List[Dict]:
        """Generate location data during stationary activities."""
        points = []
        num_points = duration_min * 6  # One point every 10 seconds

        for i in range(num_points):
            timestamp = start_time + timedelta(seconds=i * 10)

            # Base position with GPS drift
            if location['indoor']:
                # Indoor GPS drift is larger
                drift_range = 0.0001  # About 10m
                accuracy_factor = 3.0
            else:
                # Outdoor drift is smaller
                drift_range = 0.00002  # About 2m
                accuracy_factor = 1.0

            # Apply GPS drift
            lat = location['lat'] + random.uniform(-drift_range, drift_range)
            lng = location['lng'] + random.uniform(-drift_range, drift_range)

            # Special handling for specific activities
            if 'walk' in event['activity']:
                # Dog walking has more movement
                profile = self.movement['dog_walking']
                if random.random() < 0.7:  # 70% of time moving
                    speed = profile['base_speed_ms'] + random.uniform(
                        -profile['variation'], profile['variation']
                    )
                    # Larger position changes
                    lat += random.uniform(-0.0002, 0.0002)
                    lng += random.uniform(-0.0002, 0.0002)
                else:
                    speed = 0  # Dog sniffing, marking territory
            elif event['activity'] == 'pickleball':
                # Quick movements on court
                if random.random() < 0.4:  # 40% of time moving
                    speed = random.uniform(1, 3)  # Quick bursts
                    lat += random.uniform(-0.00005, 0.00005)
                    lng += random.uniform(-0.00005, 0.00005)
                else:
                    speed = 0
            elif event['activity'] == 'shopping':
                # Walking between market stalls
                if random.random() < 0.3:
                    speed = random.uniform(0.5, 1.5)
                    lat += random.uniform(-0.0001, 0.0001)
                    lng += random.uniform(-0.0001, 0.0001)
                else:
                    speed = 0
            else:
                # Stationary activity
                speed = 0

            points.append(self._create_location_point(
                lat, lng, location['altitude'], speed, timestamp, accuracy_factor
            ))

        return points

    def _create_location_point(self, lat: float, lng: float, altitude: float,
                              speed: float, timestamp: datetime,
                              accuracy_factor: float = 1.0) -> Dict:
        """Create a single location data point."""
        # Calculate accuracy based on environment
        horizontal_accuracy = random.uniform(3, 10) * accuracy_factor
        vertical_accuracy = random.uniform(4, 8) * accuracy_factor

        return {
            "latitude": round(lat, 8),
            "longitude": round(lng, 8),
            "altitude": round(altitude + random.uniform(-1, 1), 1),
            "speed": round(max(0, speed), 2),
            "horizontal_accuracy": round(horizontal_accuracy, 2),
            "vertical_accuracy": round(vertical_accuracy, 2),
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        }

    def _calculate_distance(self, lat1: float, lng1: float,
                          lat2: float, lng2: float) -> float:
        """Calculate distance between two points in kilometers."""
        R = 6371  # Earth's radius in km

        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)

        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlng / 2) ** 2)

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _estimate_travel_time(self, distance_km: float, mode: str, hour: int) -> float:
        """Estimate travel time in minutes based on distance and mode."""
        if mode == 'walking':
            return distance_km * 1000 / (self.movement['walking']['base_speed_ms'] * 60)
        elif mode == 'biking':
            return distance_km * 1000 / (self.movement['biking']['base_speed_ms'] * 60)
        elif mode == 'driving':
            # Account for traffic
            if 17 <= hour < 20:  # Evening traffic
                speed_ms = self.traffic['saturday_evening']['avg_speed_city_mph'] * 0.44704
            elif 10 <= hour < 17:
                speed_ms = self.traffic['saturday_afternoon']['avg_speed_city_mph'] * 0.44704
            else:
                speed_ms = self.traffic['saturday_morning']['avg_speed_city_mph'] * 0.44704

            # Add time for parking
            base_time = distance_km * 1000 / (speed_ms * 60)
            parking_time = random.uniform(2, 5)  # 2-5 minutes for parking

            return base_time + parking_time

        return 10  # Default fallback


def main():
    """Generate and save the location test data."""
    generator = NashvilleLocationGenerator()

    print("Generating Nashville location data...")
    data = generator.generate_day_data()

    # Save to file
    output_file = 'test_data_ios_location.json'
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Generated {len(data['data'])} location points")
    print(f"Saved to {output_file}")

    # Print summary statistics
    print("\nSummary:")
    print(f"Device ID: {data['device_id']}")
    print(f"Stream name: {data['stream_name']}")
    print(f"First timestamp: {data['data'][0]['timestamp']}")
    print(f"Last timestamp: {data['data'][-1]['timestamp']}")

    # Calculate some statistics
    speeds = [p['speed'] for p in data['data']]
    non_zero_speeds = [s for s in speeds if s > 0]

    if non_zero_speeds:
        print(f"Average speed (when moving): {sum(non_zero_speeds)/len(non_zero_speeds):.2f} m/s")
    print(f"Percentage stationary: {(len(speeds) - len(non_zero_speeds)) / len(speeds) * 100:.1f}%")


if __name__ == "__main__":
    main()
