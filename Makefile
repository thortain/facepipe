.PHONY: test demo record replay viewer

test:
	PYTHONPATH=src python3 -m unittest discover -s tests

demo:
	PYTHONPATH=src python3 -m facepipe.cli serve --source synthetic --fps 30 --web 8080

record:
	PYTHONPATH=src python3 -m facepipe.cli record --source 0 --out recordings/session.ndjson

replay:
	PYTHONPATH=src python3 -m facepipe.cli replay --in recordings/session.ndjson --emit text-udp

viewer:
	PYTHONPATH=src python3 -m facepipe.cli serve --source 0 --web 8080
