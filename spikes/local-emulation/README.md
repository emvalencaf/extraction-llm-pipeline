# Local-emulation spikes (throwaway, never merged)

Issue #25. Run: `docker run -p 5000:5000 motoserver/moto` then `python spike1_moto.py`;
`docker run -p 9324:9324 softwaremill/elasticmq` then `python spike2_elasticmq.py`;
`docker build -t sp-rie . && docker run -p 9000:8080 sp-rie` then `python spike3_rie.py`.
Needs boto3 and requests.
