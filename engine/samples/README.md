# Samples

Real outputs from the pipeline, one folder per call:

| Folder | transcript.txt | summary.json | summary.md |
|---|:-:|:-:|:-:|
| `Belrise_Industries_Limited_Q2FY27` | yes | yes | yes |
| `Kaynes_Technology_India_Limited_Q2FY26` | yes | yes | yes |
| `Zaggle_Prepaid_Ocean_Services_Limited_Q2FY27` | yes | yes | yes |
| `Tata_Motors_Passenger_Vehicles_Limited_Q2FY27` | **missing** | yes | yes |

`schema_example.json` is a **synthetic** illustration of the schema, not a real company's call.

To regenerate from your own database:

    python main.py                       # let some summaries finish
    curl -X POST "localhost:8000/v1/replay?days=45"
    python tools/dump_samples.py         # writes samples/<Company>_<Quarter>/...
