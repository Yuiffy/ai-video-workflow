"""Inspect the saved scene, pack/compress delivery, and verify its baked actions."""
import json
from pathlib import Path
import bpy

OUT = Path(__file__).resolve().parents[2] / 'outputs/sui-frisbee-3d'
bpy.ops.wm.open_mainfile(filepath=str(OUT/'sui-frisbee.blend'))
scene = bpy.context.scene
assert scene.frame_end == 384 and scene.render.fps == 24
assert (scene.render.resolution_x,scene.render.resolution_y)==(1920,1080)
assert scene.camera and scene.camera.type=='CAMERA'
assert all(i.packed_file for i in bpy.data.images if i.source=='FILE' and i.has_data)
assert scene.sequence_editor and any(s.type=='SOUND' for s in scene.sequence_editor.strips)
sounds=[{'name':s.name,'packed':bool(s.packed_file)} for s in bpy.data.sounds]
assert all(s['packed'] for s in sounds)
snapshot=[]
for frame in (1,67,85,120,133,155,212,265,271,277,384):
    scene.frame_set(frame)
    human = bpy.data.objects['Suifel_mesh']
    dog = bpy.data.objects['Dog Sui / run & jump control']
    biscuit = bpy.data.objects['Biscuit Sui / frisbee & squash control']
    snapshot.append({'frame':frame,'dog':list(dog.location),
                     'dog_scale':list(dog.scale),'biscuit':list(biscuit.location),
                     'eye_open':human.data.shape_keys.key_blocks['eye_open'].value})
assert max(s['dog'][2] for s in snapshot)>.8, 'Jump must leave the ground'
assert abs(snapshot[0]['biscuit'][0]-snapshot[4]['biscuit'][0])>3, 'Biscuit must fly'
assert min(s['dog_scale'][2] for s in snapshot)<.8, 'Ending must squash on the beat'
scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'sui-frisbee.blend'),compress=True)
report={'checks':'Camera, packed textures/audio, baked throw, jump and squash verified',
        'sounds':sounds,'snapshots':snapshot,
        'scene_file':str(OUT/'sui-frisbee.blend'),'scene_bytes':(OUT/'sui-frisbee.blend').stat().st_size}
(OUT/'scene-verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='snapshots'}))
