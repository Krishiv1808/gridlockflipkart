import cv2
import numpy as np
import random
import time

class RoadSimulator:
    def __init__(self, width=640, height=360, camera_id="CAM_021", location_name="Koramangala 18th Main"):
        self.width = width
        self.height = height
        self.camera_id = camera_id
        self.location_name = location_name
        
        # Parse camera number for dynamic, deterministic layout generation
        try:
            cam_num = int(camera_id.split('_')[1])
        except Exception:
            cam_num = 21
            
        self.cam_num = cam_num
        random.seed(101 + cam_num)
        
        # Define lanes and grass shoulders dynamically based on camera number
        if cam_num % 2 == 0:
            # 2 lanes road
            self.lanes = [120, 240]
            self.shoulder_top_y = 80
            self.shoulder_bottom_y = self.height - 60
        else:
            # 3 lanes road
            self.lanes = [100, 170, 260]
            self.shoulder_top_y = 60
            self.shoulder_bottom_y = self.height - 40
            
        # Lane separators
        self.lane_separators = []
        for i in range(len(self.lanes) - 1):
            self.lane_separators.append(int((self.lanes[i] + self.lanes[i+1]) / 2))
        
        # Dynamic No Parking Zone Polygon (the "cage" on the camera road)
        # We vary the coordinates of the polygon based on the camera number
        self.x1 = 200 + (cam_num * 7) % 80
        self.x2 = 450 + (cam_num * 13) % 80
        self.x3 = 540 + (cam_num * 17) % 60
        self.x4 = 130 + (cam_num * 19) % 60
        self.y_top = 180 + (cam_num * 3) % 40
        self.y_bottom = 290 + (cam_num * 5) % 30
        
        self.no_parking_poly = np.array([
            [self.x1, self.y_top],      # Top-left
            [self.x2, self.y_top],      # Top-right
            [self.x3, self.y_bottom],   # Bottom-right
            [self.x4, self.y_bottom]    # Bottom-left
        ], dtype=np.int32)
        
        # Vehicles state
        self.vehicles = {}
        self.next_id = 1
        
        # Active alerts list: elements are dicts with vehicle details
        self.active_alerts = {}
        self.alert_history = []
        
        # Predefined vehicle classes and colors
        self.classes = ['car', 'auto-rickshaw', 'motorcycle', 'bus', 'truck']
        self.class_colors = {
            'car': (120, 255, 120),        # Light Green
            'auto-rickshaw': (255, 200, 50), # Yellow/Orange
            'motorcycle': (50, 180, 255),    # Blue
            'bus': (255, 100, 255),         # Magenta
            'truck': (200, 200, 200)        # Gray
        }
        
        # Spawn initial parked violations deterministically based on camera_id and time first
        seed_val = sum(ord(c) for c in camera_id)
        t_sec = int(time.time())
        import random as local_rand
        r = local_rand.Random(seed_val + (t_sec // 60))

        num_violations = r.randint(1, 3)
        for i in range(num_violations):
            veh_id = seed_val * 10 + i
            veh_class = r.choice(['car', 'auto-rickshaw', 'motorcycle', 'bus'])
            duration = r.randint(20, 150) + (t_sec % 20)
            self.spawn_parked_vehicle(veh_id, veh_class, duration, slot_idx=i, total_slots=num_violations)

        # Spawn some initial driving vehicles after parked violations are placed
        for _ in range(5):
            self.spawn_vehicle(initial=True)

    def check_overlap(self, x, y, w, h, exclude_id=None, padding=5, only_front=False):
        for other_id, other_v in self.vehicles.items():
            if other_id == exclude_id:
                continue
            if only_front and other_v['x'] + other_v['w'] <= x:
                continue
            
            ox = other_v['x']
            oy = other_v['y']
            ow = other_v['w']
            oh = other_v['h']
            
            # Check overlap between (x, y, w, h) and (ox, oy, ow, oh) with padding
            if (x - padding < ox + ow and ox - padding < x + w and
                y - padding < oy + oh and oy - padding < y + h):
                return True
        return False

    def spawn_vehicle(self, initial=False):
        v_id = self.next_id
        self.next_id += 1
        
        v_class = random.choices(self.classes, weights=[0.5, 0.2, 0.2, 0.05, 0.05])[0]
        
        # Dimensions based on class
        if v_class == 'car':
            w, h = 55, 32
        elif v_class == 'auto-rickshaw':
            w, h = 42, 30
        elif v_class == 'motorcycle':
            w, h = 30, 18
        elif v_class == 'bus':
            w, h = 95, 45
        else: # truck
            w, h = 85, 40
            
        lane_idx = random.randint(0, len(self.lanes) - 1)
        y = self.lanes[lane_idx]
        
        # Horizontal position
        if initial:
            # Try to find a non-overlapping position
            found = False
            for _ in range(100):
                lane_idx = random.randint(0, len(self.lanes) - 1)
                y = self.lanes[lane_idx]
                x = random.randint(50, self.width - 100)
                if not self.check_overlap(x, y, w, h, padding=15):
                    found = True
                    break
            if not found:
                # Try with smaller padding
                for _ in range(100):
                    lane_idx = random.randint(0, len(self.lanes) - 1)
                    y = self.lanes[lane_idx]
                    x = random.randint(50, self.width - 100)
                    if not self.check_overlap(x, y, w, h, padding=5):
                        found = True
                        break
            if not found:
                self.next_id -= 1
                return
        else:
            # Try to find a lane that is not blocked at the entrance
            x = -w
            available_lanes = list(range(len(self.lanes)))
            random.shuffle(available_lanes)
            found_lane = False
            for l_idx in available_lanes:
                y = self.lanes[l_idx]
                if not self.check_overlap(x, y, w, h, padding=10):
                    lane_idx = l_idx
                    found_lane = True
                    break
            if not found_lane:
                # All lanes blocked at entrance, skip spawning this frame
                self.next_id -= 1
                return
            
        # Speed (pixels per frame)
        speed = random.uniform(3.0, 6.0)
        
        # Behavior: 15% of cars/autos/motorcycles will pull over to park
        will_park = False
        if v_class in ['car', 'auto-rickshaw', 'motorcycle'] and random.random() < 0.15:
            will_park = True
            
        self.vehicles[v_id] = {
            'id': v_id,
            'class': v_class,
            'x': x,
            'y': y,
            'w': w,
            'h': h,
            'speed': speed,
            'original_speed': speed,
            'lane_idx': lane_idx,
            'state': 'driving', # 'driving', 'parking', 'parked', 'leaving'
            'parked_frames': 0,
            'park_duration': random.randint(150, 350), # How long they stay parked
            'will_park': will_park,
            'target_y': y,
            'target_x': 0
        }

    def spawn_parked_vehicle(self, v_id, v_class, parked_duration_sec, slot_idx=0, total_slots=3):
        # Dimensions based on class
        if v_class == 'car':
            w, h = 55, 32
        elif v_class == 'auto-rickshaw':
            w, h = 42, 30
        elif v_class == 'motorcycle':
            w, h = 30, 18
        elif v_class == 'bus':
            w, h = 95, 45
        else: # truck
            w, h = 85, 40

        # Target parking spot inside the dynamic polygon ROI
        import random as local_rand
        pos_rand = local_rand.Random(v_id)

        # Deterministic vertical position with a bit of random offset
        ty = int((self.y_top + self.y_bottom) / 2) + pos_rand.randint(-15, 15)
        ty = np.clip(ty, self.y_top + 10, self.y_bottom - h - 5)
        
        weight = (ty - self.y_top) / (self.y_bottom - self.y_top)
        left_x = int(self.x1 + weight * (self.x4 - self.x1))
        right_x = int(self.x2 + weight * (self.x3 - self.x2))
        
        width_at_y = right_x - left_x
        
        # Use slot_idx to calculate tx
        fraction = (slot_idx + 0.5) / total_slots
        tx = int(left_x + fraction * width_at_y - w / 2)
        tx = np.clip(tx, left_x + 5, right_x - w - 5)

        # Start at the slot center and search nearby if there's any overlap
        found = False
        for offset in [0, 10, -10, 20, -20, 30, -30, 40, -40]:
            for y_offset in [0, 5, -5, 10, -10]:
                candidate_tx = tx + offset
                candidate_ty = ty + y_offset
                candidate_ty = np.clip(candidate_ty, self.y_top + 10, self.y_bottom - h - 5)
                
                # Recalculate boundaries for candidate_ty
                w_weight = (candidate_ty - self.y_top) / (self.y_bottom - self.y_top)
                c_left_x = int(self.x1 + w_weight * (self.x4 - self.x1))
                c_right_x = int(self.x2 + w_weight * (self.x3 - self.x2))
                candidate_tx = np.clip(candidate_tx, c_left_x + 5, c_right_x - w - 5)
                
                if not self.check_overlap(candidate_tx, candidate_ty, w, h, padding=5):
                    tx = candidate_tx
                    ty = candidate_ty
                    found = True
                    break
            if found:
                break

        parked_frames = parked_duration_sec * 12 # assuming 12 FPS

        self.vehicles[v_id] = {
            'id': v_id,
            'class': v_class,
            'x': tx,
            'y': ty,
            'w': w,
            'h': h,
            'speed': 0,
            'original_speed': pos_rand.uniform(3.0, 6.0),
            'lane_idx': 0,
            'state': 'parked',
            'parked_frames': parked_frames,
            'park_duration': parked_frames + pos_rand.randint(300, 600), # Stay parked longer
            'will_park': True,
            'target_y': ty,
            'target_x': tx
        }

        # Populate active_alerts so it is returned immediately
        current_time = time.strftime('%H:%M:%S')
        self.active_alerts[v_id] = {
            'id': v_id,
            'class': v_class,
            'location': f"{self.camera_id} - {self.location_name}",
            'duration_sec': parked_duration_sec,
            'timestamp': current_time,
            'status': 'Active'
        }

    def update(self):
        to_delete = []
        current_time = time.strftime('%H:%M:%S')
        
        # Update vehicle coordinates and state machine
        for v_id, v in list(self.vehicles.items()):
            # Check ROI overlap using center of vehicle
            cx = int(v['x'] + v['w'] / 2)
            cy = int(v['y'] + v['h'] / 2)
            is_inside_roi = cv2.pointPolygonTest(self.no_parking_poly, (cx, cy), False) >= 0
            
            if v['state'] == 'driving':
                # Collision avoidance look-ahead (keep distance to vehicle in front)
                lead_vehicle = None
                min_dist = 9999.0
                
                for other_id, other_v in self.vehicles.items():
                    if other_id == v_id:
                        continue
                    
                    # Bounding box vertical overlap check
                    y1_v, y2_v = v['y'], v['y'] + v['h']
                    y1_other, y2_other = other_v['y'], other_v['y'] + other_v['h']
                    if y1_v < y2_other and y1_other < y2_v:
                        # Lead vehicle must be in front
                        if v['x'] < other_v['x'] + other_v['w']:
                            dist = other_v['x'] - (v['x'] + v['w'])
                            if dist < min_dist:
                                min_dist = dist
                                lead_vehicle = other_v
                
                if lead_vehicle is not None and min_dist < 60.0:
                    if min_dist < 15.0:
                        v['speed'] = 0.0  # Stop to avoid collision
                    else:
                        v['speed'] = max(0.0, min(v['original_speed'], lead_vehicle['speed'] - 0.5))
                else:
                    if v['speed'] < v['original_speed']:
                        v['speed'] = min(v['original_speed'], v['speed'] + 0.2)
                
                # Safety check: if the next step would cause overlap with ANY vehicle in front, stop
                next_x = v['x'] + v['speed']
                if self.check_overlap(next_x, v['y'], v['w'], v['h'], exclude_id=v_id, padding=5, only_front=True):
                    v['speed'] = 0.0
                else:
                    v['x'] = next_x
                
                # Check if it should start parking
                if v['will_park'] and v['x'] > 180 and v['x'] < 300:
                    # Choose a non-overlapping target parking spot
                    tx, ty = 0, 0
                    found_spot = False
                    for _ in range(100):
                        ty = random.randint(self.y_top + 10, self.y_bottom - v['h'] - 5)
                        weight = (ty - self.y_top) / (self.y_bottom - self.y_top)
                        left_x = int(self.x1 + weight * (self.x4 - self.x1))
                        right_x = int(self.x2 + weight * (self.x3 - self.x2))
                        tx = random.randint(left_x + 10, right_x - v['w'] - 10)
                        
                        if not self.check_overlap(tx, ty, v['w'], v['h'], exclude_id=v_id, padding=10):
                            found_spot = True
                            break
                    
                    if found_spot:
                        v['state'] = 'parking'
                        v['target_x'] = tx
                        v['target_y'] = ty
                    else:
                        # If no spot is available, abort parking and just continue driving
                        v['will_park'] = False
                    
            elif v['state'] == 'parking':
                # Move towards the parking spot inside the ROI
                dx = v['target_x'] - v['x']
                dy = v['target_y'] - v['y']
                dist = np.sqrt(dx**2 + dy**2)
                
                if dist < 5.0:
                    v['state'] = 'parked'
                    v['speed'] = 0
                else:
                    # Move towards target
                    step_x = (dx / dist) * 2.5
                    step_y = (dy / dist) * 1.5
                    
                    next_x = v['x'] + step_x
                    next_y = v['y'] + step_y
                    
                    # Prevent overlap during movement
                    if not self.check_overlap(next_x, next_y, v['w'], v['h'], exclude_id=v_id, padding=5):
                        v['x'] = next_x
                        v['y'] = next_y
                    
            elif v['state'] == 'parked':
                # Increment stationary counter
                v['parked_frames'] += 1
                
                # Check if stationarity exceeds threshold (~80 frames = ~5-7 seconds in demo)
                stationarity_threshold = 80
                if v['parked_frames'] > stationarity_threshold:
                    # Trigger alert
                    if v_id not in self.active_alerts:
                        alert_info = {
                            'id': v_id,
                            'class': v['class'],
                            'location': f"{self.camera_id} - {self.location_name}",
                            'duration_sec': int(v['parked_frames'] / 12.0), # Assuming 12 FPS
                            'timestamp': current_time,
                            'status': 'Active'
                        }
                        self.active_alerts[v_id] = alert_info
                        self.alert_history.append(alert_info)
                    else:
                        # Update duration
                        self.active_alerts[v_id]['duration_sec'] = int(v['parked_frames'] / 12.0)
                
                # Check if it is time to leave
                if v['parked_frames'] > v['park_duration']:
                    v['state'] = 'leaving'
                    v['target_y'] = self.lanes[-1] # Go to bottom lane to merge back
                    v['speed'] = 0.5 # start slow
                    
            elif v['state'] == 'leaving':
                # Move back to bottom lane and accelerate
                dy = v['target_y'] - v['y']
                
                # Check for gap in the target lane (bottom lane) before moving vertically
                target_lane_y = self.lanes[-1]
                
                gap_blocked = False
                for other_id, other_v in self.vehicles.items():
                    if other_id == v_id:
                        continue
                    if abs(other_v['y'] - target_lane_y) < 15.0:
                        # If other_v is behind us but within 100 pixels, or overlapping
                        if other_v['x'] < v['x'] + v['w'] + 15 and other_v['x'] > v['x'] - 100:
                            gap_blocked = True
                            break
                            
                if gap_blocked:
                    v['speed'] = max(0.0, min(v['speed'], 0.5))
                    next_x = v['x'] + v['speed']
                    if not self.check_overlap(next_x, v['y'], v['w'], v['h'], exclude_id=v_id, padding=5, only_front=True):
                        v['x'] = next_x
                    else:
                        v['speed'] = 0.0
                else:
                    if v['speed'] < v['original_speed']:
                        v['speed'] += 0.05
                    
                    step_x = v['speed']
                    step_y = np.sign(dy) * 1.0 if abs(dy) > 2.0 else dy
                    
                    next_x = v['x'] + step_x
                    next_y = v['y'] + step_y
                    
                    if not self.check_overlap(next_x, next_y, v['w'], v['h'], exclude_id=v_id, padding=5):
                        v['x'] = next_x
                        v['y'] = next_y
                    else:
                        v['speed'] = 0.0
                        
                    if abs(dy) <= 2.0 and v['speed'] > 0:
                        v['state'] = 'driving'
                        v['will_park'] = False  # Don't park again
                        v['lane_idx'] = len(self.lanes) - 1
                        
                        # Resolve alert if it was active
                        if v_id in self.active_alerts:
                            self.active_alerts[v_id]['status'] = 'Resolved'
                            del self.active_alerts[v_id]
            
            # Delete if off screen
            if v['x'] > self.width + 50:
                to_delete.append(v_id)
                # Resolve alert if vehicle disappears
                if v_id in self.active_alerts:
                    self.active_alerts[v_id]['status'] = 'Resolved'
                    del self.active_alerts[v_id]
                    
        for v_id in to_delete:
            del self.vehicles[v_id]
            
        # Spawn new vehicles if count drops
        if len(self.vehicles) < 7 and random.random() < 0.08:
            self.spawn_vehicle()
            
        return list(self.active_alerts.values())
        
    def draw(self):
        # Create road canvas (Light Gray color)
        frame = np.ones((self.height, self.width, 3), dtype=np.uint8) * 220
        
        # Draw road shoulders (curbs) (Bright Green color)
        cv2.rectangle(frame, (0, 0), (self.width, self.shoulder_top_y), (200, 240, 200), -1) # grass shoulder top
        cv2.rectangle(frame, (0, self.shoulder_bottom_y), (self.width, self.height), (200, 240, 200), -1) # grass shoulder bottom
        
        # Sleek HUD Banner on top of grass shoulder
        cv2.rectangle(frame, (0, 0), (self.width, 32), (30, 30, 30), -1)
        cv2.putText(frame, f"FEED: {self.camera_id} | JURISDICTION: {self.location_name.upper()}", (12, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
        
        cv2.line(frame, (0, self.shoulder_top_y), (self.width, self.shoulder_top_y), (160, 160, 160), 2) # Curb line top
        cv2.line(frame, (0, self.shoulder_bottom_y), (self.width, self.shoulder_bottom_y), (160, 160, 160), 2) # Curb line bottom
        
        # Draw lane separators (dark gray dashed lines)
        dashed_len = 15
        gap_len = 15
        for y in self.lane_separators:
            x = 0
            while x < self.width:
                cv2.line(frame, (x, y), (x + dashed_len, y), (100, 100, 100), 1)
                x += dashed_len + gap_len
                
        # Draw No Parking Zone Polygon overlay (semi-transparent red / dashed red outline)
        overlay = frame.copy()
        cv2.fillPoly(overlay, [self.no_parking_poly], (150, 150, 255)) # Blueish/Red overlay
        # Apply transparency
        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
        
        # Draw boundary line of No Parking Zone
        cv2.polylines(frame, [self.no_parking_poly], True, (0, 0, 255), 2)
        
        # Overlay label on the No Parking Zone
        cv2.putText(frame, "NO PARKING ZONE (ROI)", (self.x1 + 10, self.y_top + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 200), 1, cv2.LINE_AA)
        
        # Draw vehicles
        for v_id, v in self.vehicles.items():
            x, y, w, h = int(v['x']), int(v['y']), int(v['w']), int(v['h'])
            
            # Bounding box color logic
            # Green = driving, Orange = stationary under threshold, Red = violation
            if v['state'] == 'parked':
                if v_id in self.active_alerts:
                    box_color = (0, 0, 255) # Bright Red
                    status_text = f"ALERT {v['parked_frames']//12}s"
                else:
                    box_color = (0, 165, 255) # Orange (stopped, checking timer)
                    status_text = f"STOPPED {v['parked_frames']//12}s"
            elif v['state'] == 'parking':
                box_color = (0, 165, 255) # Orange
                status_text = "PARKING"
            elif v['state'] == 'leaving':
                box_color = (255, 255, 0) # Cyan
                status_text = "LEAVING"
            else:
                box_color = self.class_colors[v['class']]
                status_text = "DRIVING"
                
            # Draw bounding box
            cv2.rectangle(frame, (x, y), (x + w, y + h), box_color, 2)
            
            # Draw label
            label = f"ID:{v_id:02d} {v['class'].upper()}"
            cv2.putText(frame, label, (x, y - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (50, 50, 50), 1, cv2.LINE_AA)
            cv2.putText(frame, status_text, (x, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.35, box_color, 1, cv2.LINE_AA)
            
            # If parked and in violation, draw a warning flashing circle
            if v['state'] == 'parked' and v_id in self.active_alerts:
                pulse = int(abs(np.sin(time.time() * 5)) * 6) + 3
                cv2.circle(frame, (x + w - 5, y + 5), pulse, (0, 0, 255), -1)
                
        # Draw camera HUD overlay
        cv2.rectangle(frame, (10, 10), (220, 50), (0, 0, 0), -1) # HUD background
        cv2.putText(frame, self.camera_id, (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"STATUS: ACTIVE | YOLOv8 TRACKING", (15, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (120, 255, 120), 1, cv2.LINE_AA)
        
        # Convert BGR to RGB for streamlit
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
