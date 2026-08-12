# scheduler.py
import pulp
import os
import pandas as pd
from datetime import datetime, timedelta

def run_scheduler(input_file="uploads/staff_data.xlsx"):
    staff_df = pd.read_excel(input_file)
   
    # ====================== LOAD STAFF PREFERENCES ======================
    pref_file = 'staff_preferences.csv'
    if os.path.exists(pref_file):
        try:
            pref_df = pd.read_csv(pref_file)
            
            # Merge preferences into staff_df
            for idx, row in pref_df.iterrows():
                stid = row['staff_id']
                mask = staff_df['staff_id'].astype(str) == str(stid)
                
                if mask.any():
                    staff_df.loc[mask, 'pref_night'] = row.get('pref_night', 1)
                    staff_df.loc[mask, 'max_night_shifts'] = row.get('max_night_shifts', 3)
                    staff_df.loc[mask, 'pref_off_days'] = row.get('pref_off_days', '')
                    
            print(f"✅ Loaded preferences for {len(pref_df)} staff members")
        except Exception as e:
            print(f"Warning: Could not load preferences: {e}")
    else:
        print("No staff_preferences.csv found. Using default preferences.")

    # Ensure required columns exist with defaults
    if 'pref_night' not in staff_df.columns:
        staff_df['pref_night'] = 1
    if 'max_night_shifts' not in staff_df.columns:
        staff_df['max_night_shifts'] = 3
    if 'pref_off_days' not in staff_df.columns:
        staff_df['pref_off_days'] = ''
   
    # ========================== CONFIG ==========================
    NUM_DAYS = 7
    ZONES = ['A', 'B', 'C', 'D']
    SHIFTS = ['Morning', 'Afternoon', 'Night']
    DAYS = list(range(NUM_DAYS))

    demand_config = {
        'A': {'Morning': (7, 12), 'Afternoon': (8, 13), 'Night': (6, 10)},
        'B': {'Morning': (6, 10), 'Afternoon': (7, 11), 'Night': (5, 9)},
        'C': {'Morning': (8, 14), 'Afternoon': (9, 15), 'Night': (7, 12)},
        'D': {'Morning': (5, 9), 'Afternoon': (6, 10), 'Night': (4, 8)}
    }
    high_risk_days = [2, 5]

    def get_required(zone, shift, day):
        normal, high = demand_config[zone][shift]
        return high if day in high_risk_days else normal

    # ========================== MODEL ==========================
    prob = pulp.LpProblem("DisCo_Staff_Scheduling", pulp.LpMaximize)

    assign = pulp.LpVariable.dicts("assign",
        (staff_df['staff_id'], ZONES, SHIFTS, DAYS), cat='Binary')
   
    on_call = pulp.LpVariable.dicts("on_call",
        (staff_df['staff_id'], DAYS), cat='Binary')

    # ====================== OBJECTIVE ======================
    min_cover = pulp.LpVariable.dicts("min_cover",
        ((z, s, d) for z in ZONES for s in SHIFTS for d in DAYS),
        lowBound=0, cat='Integer')

    coverage_terms = []
    preference_penalty = []

    for z in ZONES:
        for s in SHIFTS:
            for d in DAYS:
                assigned = pulp.lpSum(assign[stid][z][s][d] for stid in staff_df['staff_id'])
                required = get_required(z, s, d)
                
                prob += min_cover[(z, s, d)] <= assigned
                prob += min_cover[(z, s, d)] <= required
                coverage_terms.append(min_cover[(z, s, d)])

    for idx, row in staff_df.iterrows():
        stid = row['staff_id']
        night_shifts = pulp.lpSum(assign[stid][z]['Night'][d] for z in ZONES for d in DAYS)
        if row.get('pref_night') == 0:
            preference_penalty.append(night_shifts * 5)

    prob += (pulp.lpSum(coverage_terms) * 10 - pulp.lpSum(preference_penalty) * 2,
             "Max_Coverage_Minus_Penalties")

    # ====================== CONSTRAINTS ======================
    for stid in staff_df['staff_id']:
        for d in DAYS:
            prob += pulp.lpSum(assign[stid][z][s][d] for z in ZONES for s in SHIFTS) <= 1

    for stid in staff_df['staff_id']:
        prob += pulp.lpSum(assign[stid][z][s][d] for z in ZONES for s in SHIFTS for d in DAYS) <= 5

    for idx, row in staff_df.iterrows():
        stid = row['staff_id']
        max_night = int(row.get('max_night_shifts', 3))
        prob += pulp.lpSum(assign[stid][z]['Night'][d] for z in ZONES for d in DAYS) <= max_night

    # ====================== SOLVE ======================
    print("Solving model... (this can take 1-6 minutes)")
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=300))
   
    print("Status:", pulp.LpStatus[status])
    print("Objective:", pulp.value(prob.objective))

    if status != 1:  # 1 means Optimal
        raise Exception(f"Solver failed! Status: {pulp.LpStatus[status]}. Try reducing constraints or timeLimit.")

    # ====================== BUILD ROSTER ======================
    start_date = datetime.now()
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    roster_data = []
    for stid in staff_df['staff_id']:
        row = staff_df[staff_df['staff_id'] == stid].iloc[0]
        for d in DAYS:
            day_assignments = []
            for z in ZONES:
                for s in SHIFTS:
                    val = pulp.value(assign[stid][z][s][d])
                    if val is not None and val > 0.5:
                        day_assignments.append((z, s))
           
            real_date = start_date + timedelta(days=d)
            day_name = day_names[d]

            if day_assignments:
                z, s = day_assignments[0]
                roster_data.append({
                    'Staff_ID': stid,
                    'Name': row.get('name', 'N/A'),
                    'Department': row.get('dept', 'N/A'),
                    'Day': f"Day_{d+1}",
                    'Weekday': day_name,
                    'Date': real_date.strftime('%Y-%m-%d'),
                    'Zone': z,
                    'Shift': s,
                    'On_Call': 'No'
                })
            else:
                roster_data.append({
                    'Staff_ID': stid,
                    'Name': row.get('name', 'N/A'),
                    'Department': row.get('dept', 'N/A'),
                    'Day': f"Day_{d+1}",
                    'Weekday': day_name,
                    'Date': real_date.strftime('%Y-%m-%d'),
                    'Zone': '-',
                    'Shift': 'Off',
                    'On_Call': 'No'
                })

    roster_df = pd.DataFrame(roster_data)

    # ====================== COVERAGE REPORT ======================
    coverage_data = []
    for d in DAYS:
        day_name = day_names[d]
        for z in ZONES:
            for s in SHIFTS:
                assigned = len(roster_df[(roster_df['Day'] == f"Day_{d+1}") &
                                       (roster_df['Zone'] == z) &
                                       (roster_df['Shift'] == s)])
                required = get_required(z, s, d)
                coverage_pct = round((assigned / required * 100), 1) if required > 0 else 100
                
                coverage_data.append({
                    'Day': f"Day_{d+1}",
                    'Weekday': day_name,
                    'Zone': z,
                    'Shift': s,
                    'Required': required,
                    'Assigned': assigned,
                    'Coverage_%': coverage_pct,
                    'Status': '✅ Good' if coverage_pct >= 95 else '⚠️ Low'
                })

    coverage_df = pd.DataFrame(coverage_data)

    # ====================== SUMMARY STATISTICS ======================
    total_staff = len(staff_df)
    total_assignments = len(roster_df[roster_df['Shift'] != 'Off'])
    total_off_days = len(roster_df[roster_df['Shift'] == 'Off'])
    avg_shifts_per_staff = round(total_assignments / total_staff, 1) if total_staff > 0 else 0
    
    overall_coverage = round(coverage_df['Coverage_%'].mean(), 1)
    good_coverage_days = len(coverage_df[coverage_df['Coverage_%'] >= 95])

    summary = {
        'total_staff': total_staff,
        'total_assignments': total_assignments,
        'total_off_days': total_off_days,
        'avg_shifts_per_staff': avg_shifts_per_staff,
        'overall_coverage': overall_coverage,
        'good_coverage_days': good_coverage_days,
        'total_days': NUM_DAYS
    }

    # ====================== SAVE TO EXCEL ======================
    output_file = "DisCo_Staff_Schedule.xlsx"
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        roster_df.to_excel(writer, sheet_name="Full_Roster", index=False)
        coverage_df.to_excel(writer, sheet_name="Coverage_Report", index=False)
        staff_df.to_excel(writer, sheet_name="Staff_Master", index=False)

    print(f"✅ Schedule saved successfully! Overall Coverage: {overall_coverage}%")
    return output_file, roster_df, pulp.LpStatus[status], summary