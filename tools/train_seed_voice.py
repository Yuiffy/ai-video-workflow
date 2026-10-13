"""Single-GPU Seed-VC v2 CFM fine-tuning with resumable, retained checkpoints.

Uses a separately checked-out upstream Seed-VC. Frozen encoders stay in eval mode.
The upstream train_v2 checkpoint format is preserved for inference compatibility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--seed-root',type=Path,required=True)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--run-name',required=True)
    p.add_argument('--steps',type=int,default=1500)
    p.add_argument('--batch-size',type=int,default=2)
    p.add_argument('--save-every',type=int,default=250)
    p.add_argument('--resume',type=Path)
    args=p.parse_args()
    args.seed_root=args.seed_root.resolve();args.dataset=args.dataset.resolve()
    if args.resume:args.resume=args.resume.resolve()
    sys.path.insert(0,str(args.seed_root));os.chdir(args.seed_root)
    import numpy as np
    import torch
    import torchaudio
    from train_v2 import Trainer
    torch.set_num_threads(4)
    random.seed(20260928);np.random.seed(20260928);torch.manual_seed(20260928)
    existing=Path('runs')/args.run_name
    if existing.exists() and any(existing.glob('CFM*.pth')) and not args.resume:
        raise ValueError('Run has checkpoints; use --resume or a new run name to preserve optimizer history')
    trainer=Trainer(config_path='configs/v2/vc_wrapper.yaml',
                    pretrained_cfm_ckpt_path=str(args.resume) if args.resume else None,
                    pretrained_ar_ckpt_path=None,data_dir=str(args.dataset),
                    run_name=args.run_name,batch_size=args.batch_size,num_workers=0,
                    steps=args.steps,save_interval=args.save_every,max_epochs=1000,
                    train_cfm=True,train_ar=False,mixed_precision='bf16')
    directory=Path(trainer.log_dir)
    files=sorted(args.dataset.rglob('*.wav'))
    inventory=[{'name':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in files]
    digest=hashlib.sha256(json.dumps(inventory,sort_keys=True).encode()).hexdigest()
    step=0
    if args.resume:
        statefile=args.resume.with_suffix('.state.pt')
        state=torch.load(statefile,map_location='cpu',weights_only=False)
        if state['dataset_sha256']!=digest:raise ValueError('Dataset changed; refuse implicit resume')
        trainer.optimizer.load_state_dict(state['optimizer'])
        trainer.scheduler.load_state_dict(state['scheduler'])
        step=state['step']
        random.setstate(state['python_rng']);np.random.set_state(state['numpy_rng'])
        torch.set_rng_state(state['torch_rng']);torch.cuda.set_rng_state_all(state['cuda_rng'])
        if step>=args.steps:
            print(f'Checkpoint already reached requested step {step}',flush=True)
            return
    (directory/'dataset-inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    (directory/'run.json').write_text(json.dumps(dict(dataset=str(args.dataset),dataset_sha256=digest,
        seed=20260928,batch_size=args.batch_size,steps=args.steps,precision='bf16',
        frozen_encoders_eval=True,learning_rate=2e-5),indent=2),encoding='utf-8')
    model=trainer.accelerator.unwrap_model(trainer.model)
    model.eval();model.cfm.train();model.cfm_length_regulator.train()

    def save(epoch):
        target=directory/f'CFM_epoch_{epoch:05d}_step_{step:05d}.pth'
        state={'net':{'cfm':model.cfm.state_dict(),'length_regulator':model.cfm_length_regulator.state_dict()},
               'iters':step,'epoch':epoch}
        temp=target.with_suffix('.partial');torch.save(state,temp);temp.replace(target)
        state=dict(optimizer=trainer.optimizer.state_dict(),scheduler=trainer.scheduler.state_dict(),
                   step=step,dataset_sha256=digest,python_rng=random.getstate(),
                   numpy_rng=np.random.get_state(),torch_rng=torch.get_rng_state(),
                   cuda_rng=torch.cuda.get_rng_state_all())
        temp=target.with_suffix('.state.partial');torch.save(state,temp);temp.replace(target.with_suffix('.state.pt'))
        print(f'CHECKPOINT {target} step={step}',flush=True)
        (directory/'status.json').write_text(json.dumps(dict(step=step,target_steps=args.steps,checkpoint=str(target.resolve()))),encoding='utf-8')

    started=time.time()
    with (directory/'metrics.jsonl').open('a',encoding='utf-8') as log:
        for epoch in range(1000):
            for waves,mels,wave_lens,mel_lens in trainer.train_dataloader:
                waves16=torchaudio.functional.resample(waves,trainer.sr,16000).to(trainer.device)
                lengths16=(wave_lens.float()*16000/trainer.sr).long().to(trainer.device)
                trainer.optimizer.zero_grad(set_to_none=True)
                with trainer.accelerator.autocast():
                    _,loss=trainer.model(waves16,mels.to(trainer.device),lengths16,
                        mel_lens.to(trainer.device),forward_ar=False,forward_cfm=True)
                if not torch.isfinite(loss):raise RuntimeError(f'Non-finite loss at step {step}')
                trainer.accelerator.backward(loss)
                grad=torch.nn.utils.clip_grad_norm_(model.parameters(),1000.,error_if_nonfinite=True)
                trainer.optimizer.step();trainer.scheduler.step();step+=1
                row=dict(step=step,epoch=epoch,loss=float(loss.detach()),grad_norm=float(grad),
                         lr=trainer.scheduler.get_last_lr()[0],elapsed=time.time()-started,
                         gpu_peak_mb=torch.cuda.max_memory_allocated()/1048576)
                log.write(json.dumps(row)+'\n');log.flush()
                if step%10==0 or step==1:print(json.dumps(row),flush=True)
                if step%args.save_every==0 or step>=args.steps:save(epoch)
                if step>=args.steps:
                    (directory/'training.done').write_text(str(step),encoding='utf-8');return


if __name__=='__main__':main()
