"""Isolated, real rerun: preserve original job and dashboard state."""
import time
import sys
from pathlib import Path
import core

if __name__ == '__main__':
    original=core.DATA/'jobs'/'20261020-141648-a54e44'
    config=core.load_json(core.DATA/'settings.json')
    config.update(iterations=3,hours=0.25)
    data=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else core.ROOT/'diagnostics'/time.strftime('real-%Y%m%d-%H%M%S')
    studio=core.Studio(data)
    if len(sys.argv)>1:
        config.update(iterations=max(1,3-studio.state.get('iteration',0)),stop_when_finished=False)
    studio.start(config,original/'reference.png',core.load_json(original/'job.json')['prompt'],resume=len(sys.argv)>1)
    print('Validation data:',data,flush=True)
    last=None
    while studio.thread.is_alive():
        state=studio.snapshot()
        if state.get('message')!=last:
            last=state.get('message');print(last,flush=True)
        studio.thread.join(1)
    print(studio.snapshot()['status'],studio.snapshot()['message'],flush=True)
