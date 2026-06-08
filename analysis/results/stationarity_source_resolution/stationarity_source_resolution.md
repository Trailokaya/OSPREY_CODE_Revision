# Source-Resolution Stationarity Screen

Generated: 2026-06-08T16:20:18

## Purpose

This diagnostic complements the existing SI-F11 daily AR(1) screen by estimating Bonferroni-adjusted per-sensor period-mean intervals at the source resolution of each canonical primary matrix: hourly for Dhaka/Lucknow and official daily for Chicago.

## City Summary

| dataset_key | city | network | source_frequency | sensors | reference_mean_pm25_ugm3 | sensors_ci_excludes_reference | sensors_long_gap_gt_30d | median_source_record_uptime_pct | median_source_ar1_effective_n | median_source_lag1_autocorrelation | max_longest_gap_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dhaka_lcs | Dhaka | LCS | hourly | 35 | 55.147 | 10 | 5 | 87.637 | 242.940 | 0.935 | 46.500 |
| lucknow_lcs | Lucknow | LCS | hourly | 71 | 61.802 | 23 | 37 | 73.219 | 177.051 | 0.959 | 326.708 |
| chicago_lcs_corrected_no_collocation | Chicago | LCS corrected | official_daily | 277 | 10.253 | 11 | 11 | 99.634 | 77.793 | 0.554 | 181.000 |

## Flagged Or Long-Gap Sensors

| city | sensor_id | station_name | period_mean_pm25_ugm3 | reference_mean_pm25_ugm3 | mean_minus_reference_ugm3 | source_record_uptime_pct | lag1_autocorrelation_source_resolution | ar1_effective_n_source_resolution | ci_excludes_reference | longest_missing_gap_days | long_gap_gt_30d |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Chicago | DYWWS0378 | Uptown 4 | 7.392 | 10.253 | -2.861 | 91.941 | 0.425 | 101.397 | True | 21.000 | False |
| Chicago | DWGYM0810 | Avalon Park 1 | 18.998 | 10.253 | 8.745 | 87.912 | 0.491 | 81.868 | True | 7.000 | False |
| Chicago | DWBTT8209 | Edison Park 1 | 7.682 | 10.253 | -2.571 | 98.535 | 0.580 | 71.518 | True | 2.000 | False |
| Chicago | DMIYV7889 | O'Hare 2 | 8.080 | 10.253 | -2.173 | 97.802 | 0.568 | 73.510 | True | 2.000 | False |
| Chicago | DKIJX6114 | Lincoln Square 1 | 8.364 | 10.253 | -1.889 | 98.901 | 0.551 | 78.100 | True | 2.000 | False |
| Chicago | DMMAG3845 | Riverdale 3 | 4.922 | 10.253 | -5.331 | 99.634 | 0.388 | 119.961 | True | 1.000 | False |
| Chicago | DGHRH9009 | Gage Park 1 | 7.318 | 10.253 | -2.935 | 99.634 | 0.608 | 66.265 | True | 1.000 | False |
| Chicago | DJKZD4256 | Morgan Park 3 | 7.646 | 10.253 | -2.607 | 99.634 | 0.520 | 85.898 | True | 1.000 | False |
| Chicago | DRUBP9408 | South Deering 2 | 8.174 | 10.253 | -2.079 | 99.634 | 0.381 | 121.970 | True | 1.000 | False |
| Chicago | DMARJ5120 | Hyde Park 1 | 8.282 | 10.253 | -1.972 | 99.634 | 0.510 | 88.370 | True | 1.000 | False |
| Chicago | DZLAV7766 | Austin 4 | 13.428 | 10.253 | 3.175 | 99.634 | 0.577 | 73.044 | True | 1.000 | False |
| Chicago | DJJWX4142 | South Lawndale 4 | 8.617 | 10.253 | -1.637 | 21.245 | 0.540 | 17.322 | False | 181.000 | True |
| Chicago | DMAEX1156 | South Deering 9 | 9.957 | 10.253 | -0.296 | 36.996 | 0.619 | 23.793 | False | 172.000 | True |
| Chicago | DEYGE9157 | South Deering 10 | 8.781 | 10.253 | -1.472 | 53.480 | 0.611 | 35.248 | False | 109.000 | True |
| Chicago | DSSQU9498 | Near North Side 4 | 10.498 | 10.253 | 0.244 | 61.172 | 0.562 | 46.794 | False | 104.000 | True |
| Chicago | DDVZB7943 | Hyde Park 2 | 8.411 | 10.253 | -1.842 | 70.330 | 0.479 | 67.608 | False | 80.000 | True |
| Chicago | DUVHI0112 | Loop 1 | 9.187 | 10.253 | -1.066 | 35.165 | 0.645 | 20.742 | False | 77.000 | True |
| Chicago | DXHCB5919 | Uptown 2 | 9.426 | 10.253 | -0.828 | 61.905 | 0.560 | 47.679 | False | 69.000 | True |
| Chicago | DYDVV6312 | Humboldt Park 2 | 11.201 | 10.253 | 0.947 | 78.022 | 0.550 | 61.807 | False | 59.000 | True |
| Chicago | DFQDK6326 | Beverly 1 | 11.849 | 10.253 | 1.596 | 66.300 | 0.505 | 59.540 | False | 52.000 | True |
| Chicago | DMLRY2750 | North Park 1 | 9.156 | 10.253 | -1.097 | 86.447 | 0.514 | 75.791 | False | 35.000 | True |
| Chicago | DFIBC1899 | South Deering 7 | 10.740 | 10.253 | 0.486 | 77.289 | 0.615 | 50.364 | False | 34.000 | True |
| Dhaka | 81432151072 | 63. Khilkhet | 25.026 | 55.147 | -30.121 | 91.838 | 0.908 | 386.238 | True | 20.667 | False |
| Dhaka | 81432151014 | 64. Satarkul | 86.452 | 55.147 | 31.305 | 85.137 | 0.911 | 347.208 | True | 20.667 | False |
| Dhaka | 81432150006 | 31. Rupnogor high school, Pallabi | 36.829 | 55.147 | -18.318 | 76.336 | 0.879 | 431.216 | True | 20.542 | False |
| Dhaka | 81432151022 | 34. Farmgate | 63.934 | 55.147 | 8.787 | 88.756 | 0.771 | 1005.456 | True | 20.542 | False |
| Dhaka | 81432124031 | 1. Siddeshwari  | 39.166 | 55.147 | -15.981 | 91.655 | 0.945 | 225.012 | True | 17.792 | False |
| Dhaka | 81432130042 | 15. Mohammadpur | 43.363 | 55.147 | -11.784 | 92.432 | 0.945 | 229.384 | True | 16.958 | False |
| Dhaka | 81432130035 | 12. Bashundhara RA | 39.600 | 55.147 | -15.547 | 61.701 | 0.932 | 190.240 | True | 12.333 | False |
| Dhaka | 81432130017 | 8. Vasantek | 73.008 | 55.147 | 17.861 | 74.760 | 0.901 | 342.272 | True | 11.417 | False |
| Dhaka | 81432130021 | 11. Cantonment, Balurghat | 67.442 | 55.147 | 12.295 | 91.769 | 0.776 | 1015.540 | True | 3.167 | False |
| Dhaka | 81432130014 | 16. Narayangonj, Gognogor | 79.629 | 55.147 | 24.482 | 99.669 | 0.946 | 242.940 | True | 0.167 | False |
| Dhaka | 81432151044 | 75. Uttara, Rd 12 | 46.874 | 55.147 | -8.274 | 72.249 | 0.954 | 162.282 | False | 46.500 | True |
| Dhaka | 81432151062 | 74. CARS | 51.681 | 55.147 | -3.466 | 86.678 | 0.957 | 194.692 | False | 38.583 | True |
| Dhaka | 81432152006 | 73. Science Lab | 60.379 | 55.147 | 5.232 | 87.557 | 0.950 | 196.880 | False | 38.583 | True |
| Dhaka | 81432151066 | 41. Banani  | 60.752 | 55.147 | 5.605 | 80.068 | 0.957 | 179.846 | False | 35.375 | True |
| Dhaka | 81432151048 | 33. DU Club | 48.220 | 55.147 | -6.927 | 78.174 | 0.914 | 308.326 | False | 34.625 | True |
| Lucknow | 81432144008 | Chak Ganjaria | 34.473 | 61.802 | -27.329 | 14.247 | 0.948 | 33.188 | True | 173.708 | True |
| Lucknow | 81432147060 | Shanti Nagar | 24.818 | 61.802 | -36.984 | 52.854 | 0.932 | 163.032 | True | 162.333 | True |
| Lucknow | 81432144016 | Lohiya college | 42.546 | 61.802 | -19.256 | 8.938 | 0.775 | 99.348 | True | 150.542 | True |
| Lucknow | 81432131007 | Charbagh | 30.913 | 61.802 | -30.889 | 61.199 | 0.968 | 137.462 | True | 139.542 | True |
| Lucknow | 81432144031 | Kalyanpur | 82.046 | 61.802 | 20.244 | 55.320 | 0.943 | 141.919 | True | 104.458 | True |
| Lucknow | 81432131001 | Transport Nagar | 32.225 | 61.802 | -29.577 | 58.813 | 0.980 | 132.103 | True | 100.458 | True |
| Lucknow | 81432144007 | Dashauli | 39.579 | 61.802 | -22.224 | 58.676 | 0.979 | 131.795 | True | 99.875 | True |
| Lucknow | 81432147055 | Daliganj | 50.223 | 61.802 | -11.580 | 59.155 | 0.860 | 389.789 | True | 97.833 | True |
| Lucknow | 81432131012 | Vrindavan Yojana | 81.299 | 61.802 | 19.497 | 65.057 | 0.929 | 210.167 | True | 93.708 | True |
| Lucknow | 81432147069 | Hazratganj_NBRI | 39.178 | 61.802 | -22.624 | 66.838 | 0.976 | 150.128 | True | 93.375 | True |
| Lucknow | 81432144019 | Mubarakpur | 84.014 | 61.802 | 22.212 | 81.450 | 0.966 | 182.949 | True | 66.958 | True |
| Lucknow | 81432147001 | Arjunganj | 89.196 | 61.802 | 27.394 | 69.795 | 0.971 | 156.769 | True | 63.083 | True |
| Lucknow | 81432147039 | Nagram | 100.987 | 61.802 | 39.185 | 29.600 | 0.811 | 270.697 | True | 47.375 | True |
| Lucknow | 81432130004 | B R Ambedkar University, Lucknow - UPPCB | 44.419 | 61.802 | -17.384 | 78.539 | 0.974 | 176.410 | True | 39.167 | True |
| Lucknow | 81432147045 | Qaiserbagh | 103.127 | 61.802 | 41.325 | 71.244 | 0.919 | 264.174 | True | 31.583 | True |
| Lucknow | 81432147065 | Balaganj | 114.788 | 61.802 | 52.986 | 51.279 | 0.949 | 116.757 | True | 31.292 | True |
| Lucknow | 81432147040 | Amethi, jagdishpur | 83.498 | 61.802 | 21.695 | 82.203 | 0.941 | 220.770 | True | 25.375 | False |
| Lucknow | 81432131009 | Vipul Khand | 43.688 | 61.802 | -18.114 | 71.792 | 0.973 | 161.256 | True | 4.083 | False |
| Lucknow | 81432131005 | Husainabad | 47.586 | 61.802 | -14.216 | 97.180 | 0.873 | 575.738 | True | 3.042 | False |
| Lucknow | 81432131013 | Kakori | 48.015 | 61.802 | -13.787 | 95.845 | 0.979 | 215.282 | True | 1.167 | False |
| Lucknow | 81432147004 | Anand Nagar | 48.528 | 61.802 | -13.274 | 96.256 | 0.964 | 216.205 | True | 0.958 | False |
| Lucknow | 81432147072 | Haroiya | 48.431 | 61.802 | -13.372 | 98.596 | 0.924 | 338.868 | True | 0.750 | False |
| Lucknow | 81432147046 | CMS_IndNgr | 49.386 | 61.802 | -12.416 | 97.808 | 0.952 | 219.692 | True | 0.500 | False |
| Lucknow | 81432147056 | Rajajipuram-II | 45.112 | 61.802 | -16.691 | 4.521 | 0.868 | 27.948 | False | 326.708 | True |
| Lucknow | 81432144006 | Jankipuram Vistar | 49.371 | 61.802 | -12.431 | 61.598 | 0.973 | 138.359 | False | 108.833 | True |
| Lucknow | 81432144024 | Umarbhari | 43.839 | 61.802 | -17.963 | 30.468 | 0.984 | 68.436 | False | 94.708 | True |
| Lucknow | 81432147041 | UniWrld IndNagar | 64.427 | 61.802 | 2.624 | 67.648 | 0.958 | 151.949 | False | 83.167 | True |
| Lucknow | 81432147044 | Rahta | 75.749 | 61.802 | 13.947 | 67.374 | 0.952 | 151.333 | False | 75.708 | True |
| Lucknow | 81432144027 | CIMAP | 57.458 | 61.802 | -4.345 | 52.237 | 0.974 | 117.333 | False | 67.458 | True |
| Lucknow | 81432131015 | IITR-Hazratganj | 72.823 | 61.802 | 11.021 | 67.317 | 0.969 | 151.205 | False | 60.708 | True |
| Lucknow | 81432144021 | LPS Jankipuram | 55.968 | 61.802 | -5.835 | 64.909 | 0.970 | 145.795 | False | 60.500 | True |
| Lucknow | 81432144023 | Mohammadpur | 64.011 | 61.802 | 2.209 | 78.824 | 0.971 | 177.051 | False | 59.833 | True |
| Lucknow | 81432131002 | Dubagga | 59.131 | 61.802 | -2.671 | 65.936 | 0.957 | 148.103 | False | 58.167 | True |
| Lucknow | 81432131011 | Aminabad | 59.487 | 61.802 | -2.315 | 70.525 | 0.966 | 158.410 | False | 56.917 | True |
| Lucknow | 81432147038 | Mall | 56.159 | 61.802 | -5.644 | 59.829 | 0.979 | 134.385 | False | 49.333 | True |
| Lucknow | 81432147061 | Para | 59.182 | 61.802 | -2.620 | 73.219 | 0.958 | 164.462 | False | 49.125 | True |
| Lucknow | 81432131014 | Gomti Nagar, Lucknow - UPPCB | 63.623 | 61.802 | 1.821 | 70.091 | 0.969 | 157.436 | False | 48.750 | True |
| Lucknow | 81432147076 | Jopling | 64.333 | 61.802 | 2.531 | 85.183 | 0.967 | 191.333 | False | 47.583 | True |
| Lucknow | 81432144014 | Nigoha | 80.987 | 61.802 | 19.185 | 52.763 | 0.977 | 118.513 | False | 43.208 | True |
| Lucknow | 81432147034 | Talkatora_BPS | 98.835 | 61.802 | 37.033 | 27.340 | 0.957 | 61.410 | False | 42.542 | True |
| Lucknow | 81432130005 | Rajendra Nagar-II | 79.230 | 61.802 | 17.428 | 80.993 | 0.940 | 220.797 | False | 39.583 | True |
| Lucknow | 81432147053 | Ambalika | 71.768 | 61.802 | 9.965 | 32.272 | 0.976 | 72.487 | False | 38.000 | True |
| Lucknow | 81432144026 | Itaunja | 56.650 | 61.802 | -5.153 | 80.297 | 0.961 | 180.359 | False | 37.500 | True |
| Lucknow | 81432130008 | Lucknow Cantonment | 54.655 | 61.802 | -7.147 | 80.285 | 0.939 | 220.988 | False | 32.167 | True |

## Interpretation

- This remains an approximation to full GLS-AR(1), but it uses the highest canonical resolution available for each primary dataset.
- A CI excluding the deployed-network reference mean is a stationarity sensitivity flag, not automatic evidence of a faulty sensor.
- Long gaps remain important because they can shift a sensor's period mean by removing seasonal or episodic high-pollution periods.
- The manuscript should present this as a robustness/stationarity screen, not as proof that all sensors sample an identical underlying mean.
