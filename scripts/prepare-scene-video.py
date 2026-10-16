#!/usr/bin/env python3
"""Prepare all scenes using the same service as the frontend. Status is read-only."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.video_preparation_api import PreparationRequest,execute_preparation,get_preparation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--phase',choices=['images','video'],default='video')
    parser.add_argument('--review-revision',type=int,default=0,choices=range(4))
    parser.add_argument('--execute',action='store_true',help='Authorize the configured author and bounded image repair calls')
    parser.add_argument('--scene-id',action='append',dest='scene_ids')
    parser.add_argument('--target-video-model',choices=['higgsfield_kling_standard'])
    parser.add_argument('--max-images',type=int,default=0)
    parser.add_argument('--max-cost-usd',type=float)
    parser.add_argument('--fixed-image',action='append',default=[])
    args=parser.parse_args()
    if args.execute:
        req=PreparationRequest(run_id=args.run_id,phase=args.phase,review_revision=args.review_revision,scene_ids=args.scene_ids,max_image_generations=args.max_images,
            max_cost_usd=args.max_cost_usd,fixed_image_paths=args.fixed_image,target_video_model=args.target_video_model)
        result=asyncio.run(execute_preparation(req))
    else:result=asyncio.run(get_preparation(args.run_id,args.phase))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status'] not in ('failed','needs_input') else 1

if __name__=='__main__':
    raise SystemExit(main())
