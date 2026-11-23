import math

def _hav_km(a1, o1, a2, o2):
    r = 6371.0
    p1, p2 = math.radians(a1), math.radians(a2)
    dp, dl = math.radians(a2 - a1), math.radians(o2 - o1)
    return 2 * r * math.asin(math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))

METRO_STATIONS = [
    ("Versova Metro", 19.1314, 72.8213), ("DN Nagar Metro", 19.1243, 72.8315),
    ("Azad Nagar Metro", 19.1268, 72.8380), ("Andheri Metro", 19.1197, 72.8464),
    ("WEH Metro", 19.1155, 72.8562), ("Chakala Metro", 19.1112, 72.8635),
    ("Marol Naka Metro", 19.1082, 72.8798), ("Saki Naka Metro", 19.1030, 72.8880),
    ("Asalpha Metro", 19.0968, 72.8980), ("Ghatkopar Metro", 19.0868, 72.9082),
    ("Dahisar East Metro", 19.2502, 72.8593), ("Borivali West Metro", 19.2292, 72.8452),
    ("Kandivali West Metro", 19.2059, 72.8364), ("Malad West Metro", 19.1864, 72.8360),
    ("Goregaon West Metro", 19.1665, 72.8366), ("Oshiwara Metro", 19.1490, 72.8345),
    ("Lower Oshiwara Metro", 19.1415, 72.8330),
    ("Ovaripada Metro", 19.2420, 72.8635), ("Magathane Metro", 19.2185, 72.8645),
    ("Poisar Metro", 19.2050, 72.8650), ("Kurar Metro", 19.1865, 72.8615),
    ("Aarey Metro", 19.1650, 72.8565), ("Jogeshwari East Metro", 19.1370, 72.8560),
    ("Gundavali Metro", 19.1155, 72.8562),
    ("Cuffe Parade Metro", 18.9128, 72.8214), ("Vidhan Bhavan Metro", 18.9265, 72.8240),
    ("Churchgate Metro", 18.9322, 72.8264), ("Hutatma Chowk Metro", 18.9335, 72.8325),
    ("Kalbadevi Metro", 18.9475, 72.8295), ("Grant Road Metro", 18.9625, 72.8170),
    ("Mumbai Central Metro", 18.9712, 72.8195), ("Mahalaxmi Metro", 18.9830, 72.8210),
    ("Worli Metro", 19.0055, 72.8235), ("Siddhivinayak Metro", 19.0170, 72.8305),
    ("Dadar Metro", 19.0215, 72.8390), ("Shitladevi Metro", 19.0345, 72.8405),
    ("Dharavi Metro", 19.0445, 72.8535), ("BKC Metro", 19.0655, 72.8655),
    ("Bandra Colony Metro", 19.0750, 72.8595), ("Santacruz Metro", 19.0850, 72.8520),
    ("CSMIA T1 Metro", 19.0920, 72.8565), ("Sahar Road Metro", 19.0990, 72.8690),
    ("CSMIA T2 Metro", 19.0980, 72.8745), ("SEEPZ Metro", 19.1245, 72.8740),
    ("Aarey JVLR Metro", 19.1390, 72.8780),
    ("Chembur Metro", 19.0550, 72.9000), ("Diamond Garden Metro", 19.0510, 72.9075),
    ("Mandale Metro", 19.0525, 72.9310),
    ("CBD Belapur Metro", 19.0185, 73.0385), ("Kharghar Sector 11 Metro", 19.0425, 73.0685),
    ("Central Park Kharghar Metro", 19.0575, 73.0695), ("Pendhar Metro", 19.0790, 73.0815),
]

LOCAL_TRAINS = [
    ("Churchgate (WR)", 18.9355, 72.8273), ("Marine Lines (WR)", 18.9445, 72.8238),
    ("Charni Road (WR)", 18.9518, 72.8183), ("Grant Road (WR)", 18.9633, 72.8160),
    ("Mumbai Central (WR)", 18.9690, 72.8194), ("Mahalaxmi (WR)", 18.9825, 72.8240),
    ("Lower Parel (WR)", 18.9958, 72.8305), ("Prabhadevi (WR)", 19.0075, 72.8362),
    ("Dadar (WR/CR)", 19.0178, 72.8428), ("Matunga Road (WR)", 19.0278, 72.8465),
    ("Mahim (WR)", 19.0405, 72.8465), ("Bandra (WR)", 19.0544, 72.8402),
    ("Khar Road (WR)", 19.0697, 72.8400), ("Santacruz (WR)", 19.0816, 72.8415),
    ("Vile Parle (WR)", 19.0996, 72.8439), ("Andheri (WR)", 19.1197, 72.8468),
    ("Jogeshwari (WR)", 19.1363, 72.8489), ("Goregaon (WR)", 19.1645, 72.8492),
    ("Malad (WR)", 19.1869, 72.8489), ("Kandivali (WR)", 19.2045, 72.8518),
    ("Borivali (WR)", 19.2291, 72.8573), ("Dahisar (WR)", 19.2500, 72.8595),
    ("Mira Road (WR)", 19.2810, 72.8562), ("Bhayandar (WR)", 19.3114, 72.8525),
    ("CSMT (CR)", 18.9401, 72.8355), ("Byculla (CR)", 18.9759, 72.8331),
    ("Parel (CR)", 19.0095, 72.8376), ("Matunga (CR)", 19.0275, 72.8505),
    ("Sion (CR)", 19.0466, 72.8633), ("Kurla (CR)", 19.0655, 72.8794),
    ("Vidyavihar (CR)", 19.0796, 72.8973), ("Ghatkopar (CR)", 19.0859, 72.9082),
    ("Vikhroli (CR)", 19.1112, 72.9277), ("Kanjurmarg (CR)", 19.1292, 72.9284),
    ("Bhandup (CR)", 19.1422, 72.9378), ("Nahur (CR)", 19.1544, 72.9465),
    ("Mulund (CR)", 19.1722, 72.9562), ("Thane (CR)", 19.1861, 72.9758),
    ("Wadala Road (HR)", 19.0160, 72.8590), ("Chembur (HR)", 19.0623, 72.9008),
    ("Vashi (HR)", 19.0642, 72.9990), ("Sanpada (HR)", 19.0660, 73.0095),
    ("Nerul (HR)", 19.0338, 73.0185), ("Seawoods (HR)", 19.0222, 73.0190),
    ("CBD Belapur (HR)", 19.0188, 73.0394), ("Kharghar (HR)", 19.0258, 73.0598),
    ("Airoli (TH)", 19.1585, 72.9995), ("Ghansoli (TH)", 19.1245, 73.0010),
    ("Kopar Khairane (TH)", 19.1030, 73.0050), ("Panvel (HR)", 18.9906, 73.1208),
]

HUB_COORDS = {
    "bkc": (19.0658, 72.8645),
    "lower_parel": (18.9977, 72.8300),
    "nariman_point": (18.9256, 72.8242),
    "andheri_seepz": (19.1245, 72.8740),
    "powai": (19.1197, 72.9051),
    "goregaon_nesco": (19.1510, 72.8535),
}

def enrich_transit_context(socs):
    fixed_far, filled = 0, 0
    for s in socs:
        lat, lng = s.get("lat"), s.get("lng")
        if not lat or not lng:
            continue
        lat, lng = float(lat), float(lng)
        ctx = s.get("mumbai_context")
        if not isinstance(ctx, dict):
            ctx = {}
            s["mumbai_context"] = ctx

        m_name, m_km = min(((n, _hav_km(lat, lng, a, o)) for n, a, o in METRO_STATIONS), key=lambda x: x[1])
        m_walk = max(2, int(round(m_km * 1.3 * 12)))
        cur_m = ctx.get("nearest_metro")
        if isinstance(cur_m, dict) and (cur_m.get("walk_min") or 0) > 45:
            ctx.pop("nearest_metro", None)
            fixed_far += 1
        if m_walk <= 45 and (not ctx.get("nearest_metro") or (ctx["nearest_metro"].get("walk_min") or 999) > m_walk):
            ctx["nearest_metro"] = {"name": m_name, "distance_m": int(round(m_km * 1000)), "walk_min": m_walk}
            filled += 1

        t_name, t_km = min(((n, _hav_km(lat, lng, a, o)) for n, a, o in LOCAL_TRAINS), key=lambda x: x[1])
        t_walk = max(2, int(round(t_km * 1.3 * 12)))
        cur_l = ctx.get("nearest_local")
        if not isinstance(cur_l, dict) or (cur_l.get("walk_min") or 999) > 60:
            ctx["nearest_local"] = {"name": t_name, "distance_m": int(round(t_km * 1000)), "walk_min": t_walk}
            filled += 1
        ctx.pop("nearest_train", None)

        hubs = ctx.get("commute_hubs_min")
        if not isinstance(hubs, dict):
            hubs = {}
            ctx["commute_hubs_min"] = hubs
        comm = s.get("commutes")
        if not isinstance(comm, dict):
            comm = {}
            s["commutes"] = comm
        for hk, (hlat, hlng) in HUB_COORDS.items():
            if not hubs.get(hk):
                dk = _hav_km(lat, lng, hlat, hlng)
                mins = max(8, min(140, int(round(9 + dk * 3.1))))
                hubs[hk] = mins
                comm[hk if hk != "andheri_seepz" else "seepz"] = mins
        if not comm.get("bkc"):
            comm["bkc"] = hubs["bkc"]
        if not ctx.get("monsoon_flood_risk"):
            ctx["monsoon_flood_risk"] = "low"
    return fixed_far, filled
