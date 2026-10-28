# Ground Robot Control for Data Acquisition

MSc project for D7016B Industrial AI and eMaintenance (Part II), Luleå University of Technology.

A Waveshare UGV-01 tracked robot drives along a wall, stops at fixed waypoints and photographs the wall for maintenance inspection. At each waypoint it checks that the new photo overlaps enough with the previous one, and backs up to re-shoot if it does not. After the run, a crack-segmentation model screens every photo and a draft condition report is written. The report is only valid after a person has reviewed every finding and signed it.

The robot was tested on a 5 m wall section of the Björkskataleden underpass in Luleå at 40, 60 and 100 cm from the wall.

## How it works

1. **Capture**: 25 legs of 0.2 m (26 waypoints, 5.0 m), three photos per waypoint at three pan angles.
2. **Self-check**: SIFT feature matches between neighbouring waypoints, checked with RANSAC. Below 25 verified matches the robot backs up 0.1, 0.2 and then 0.3 m and re-shoots.
3. **Screening**: a YOLO segmentation model trained on a public crack dataset and fine-tuned with 50 crack-free photos of the site.
4. **Draft report**: a Word report with location, size, severity, action and deadline for each finding.
5. **Review**: a person confirms or rejects each finding and signs the report.

Position along the wall comes from the waypoint number (waypoint 10 = 2.0 m from the start). There is no GPS.

## Files

| File | What it does |
|---|---|
| `move_robot.py` | Movement and camera commands to the robot (JSON over HTTP) |
| `capture.py` | Takes a photo on the robot's Raspberry Pi and copies it to `photos/` |
| `self_check.py` | Blur check and overlap check (verified feature matches) |
| `waypoint_route.py` | The inspection route with the self-check and re-shoots |
| `run_inspection.py` | One command: runs the route, then writes the draft report |
| `generate_condition_report.py` | Crack screening and the draft condition report (v3) |
| `calib_capture.py` | Checkerboard photos for a lens calibration |
| `analysis/compare_report_fix.py` | Findings with the old (v2) and new (v3) report rules, run by run |
| `analysis/make_figures_24oct.py` | Figures and CSV files from the condition reports |
| `analysis/make_fig13_reshoot.py` | Figure of the self-check on site |
| `analysis/plot_overlap_log.py` | Plots of `overlap_log.csv`, one chart per run |
| `training/train_crack_model.py` | How the crack model was trained (Google Colab) |

## Running an inspection

The Mac must be connected to the robot's own Wi-Fi. The robot's controller is at `192.168.4.1` and the Raspberry Pi at `192.168.4.50` (SSH key login, user `ugv`).

```
pip3 install -r requirements.txt
python3 move_robot.py                      # connection check
python3 capture.py                         # test photo
python3 run_inspection.py --distance 40    # full run and draft report
```

The crack model `best_v2.pt` and the LTU logo `ltu_logo.png` must be in the project folder. Photos are saved in `photos/` and reports in `reports/<run ID>/`. Neither is included in this repository.

A report can also be written again for an earlier run:

```
python3 generate_condition_report.py photos --run 20261024_144211 --distance 40
```

## Report rules in v3

The first site tests gave 152 findings in 20 reports, every one rated High, and none of them a real crack. Three rules were added to the report generator:

1. A crack width is only graded when the photo can measure it. At 40 cm one pixel is 0.5 mm and the model's outline is about 32 pixels wide whatever it finds, so the width cannot be measured and the finding is marked Unverified for manual review instead of High.
2. Detections in the far, angled part of each wall photo are not counted. That part of the wall is seen square-on from the next waypoint.
3. Known recurring features at this site (the deck edge and two joint lines) are listed separately and not counted as defects.

`analysis/compare_report_fix.py` shows the effect of each rule on the site runs. Rules 2 and 3 were worked out from the same runs, so their effect on new data is not yet tested.

## Limitations

- One site and one wall; the two real cracks found by hand (about 0.2 to 0.5 mm wide) are below one pixel at 40 cm.
- The robot drifts sideways over a run; there is no distance sensor.
- Direct sunlight washes out the photos.

## Acknowledgements

Supervisor: Amit Patwardhan. Course coordinator: Ravdeep Kour. The AI assistant Claude (Anthropic) was used for coding support and analysis.
