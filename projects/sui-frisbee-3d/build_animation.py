"""An editable, deterministic 16-second Blender short. Run with Blender 4.5."""
import argparse
import bmesh
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Euler, Vector

BASE = Path(__file__).resolve().parents[2]
OUT = BASE / 'outputs/sui-frisbee-3d'
FPS, SECONDS = 24, 16
TAU = math.tau


def smooth(a, b, t):
    u = max(0, min(1, (t-a)/(b-a)))
    return u*u*(3-2*u)


def mix(a, b, u):
    return a + (b-a)*u


def material(name, color, roughness=.7, emission=0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = roughness
    p.inputs['Specular IOR Level'].default_value = .25
    p.inputs['Emission Color'].default_value = (*color, 1)
    p.inputs['Emission Strength'].default_value = emission
    return m


def empty(name, loc=(0,0,0), parent=None):
    ob = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(ob)
    ob.parent = parent
    ob.location = loc
    ob.empty_display_type = 'PLAIN_AXES'
    ob.empty_display_size = .15
    return ob


def sphere(name, loc, scale, mat, parent=None, segments=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=16)
    ob = bpy.context.object
    ob.name = name
    ob.parent = parent
    ob.location, ob.scale = loc, scale
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def cylinder(name, loc, radius, depth, mat, parent=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=radius, depth=depth)
    ob = bpy.context.object
    ob.name = name
    ob.parent = parent
    ob.location = loc
    ob.data.materials.append(mat)
    bevel = ob.modifiers.new('Soft baked edges', 'BEVEL')
    bevel.width, bevel.segments = min(.04, depth*.3), 3
    ob.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return ob


def tube(name, pts, radius, mat, parent=None):
    cv = bpy.data.curves.new(name, 'CURVE')
    cv.dimensions, cv.resolution_u = '3D', 12
    cv.bevel_depth, cv.bevel_resolution = radius, 3
    cv.use_fill_caps = True
    spl = cv.splines.new('BEZIER')
    spl.bezier_points.add(len(pts)-1)
    for p, xyz in zip(spl.bezier_points, pts):
        p.co = xyz
        p.handle_left_type = p.handle_right_type = 'AUTO'
    ob = bpy.data.objects.new(name, cv)
    bpy.context.collection.objects.link(ob)
    ob.parent = parent
    ob.data.materials.append(mat)
    return ob


def mesh(name, verts, faces, mat, parent=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    ob = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(ob)
    ob.parent = parent
    ob.data.materials.append(mat)
    return ob


def set_keys(ob, frame, paths=('location','rotation_euler','scale')):
    for path in paths:
        ob.keyframe_insert(data_path=path, frame=frame)


def pose(arm, name, degrees, frame):
    pb = arm.pose.bones.get(name)
    if not pb:
        return
    q = pb.bone.matrix_local.to_quaternion()
    delta = Euler(tuple(math.radians(v) for v in degrees), 'XYZ').to_quaternion()
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = q.inverted() @ delta @ q
    pb.keyframe_insert(data_path='rotation_quaternion', frame=frame)


def shape(ob, name, value, frame=None):
    if ob.data.shape_keys and name in ob.data.shape_keys.key_blocks:
        k = ob.data.shape_keys.key_blocks[name]
        k.value = value
        if frame is not None:
            k.keyframe_insert('value', frame=frame)


def toon_imported_materials():
    """Keep the supplied texture colors; use opaque/cutout cel shading."""
    for m in [bpy.data.materials.get(n) for n in ('Acc','Body_skin','Body_eye','Body_alpha','Cloth','Hair')]:
        if not m:
            continue
        old = m.node_tree.nodes.get('mmd_base_tex')
        img = old.image if old else None
        m.use_nodes = True
        n, links = m.node_tree.nodes, m.node_tree.links
        n.clear()
        tex = n.new('ShaderNodeTexImage')
        tex.image = img
        diffuse = n.new('ShaderNodeBsdfDiffuse')
        diffuse.inputs['Color'].default_value = (1,1,1,1)
        rgb = n.new('ShaderNodeShaderToRGB')
        links.new(diffuse.outputs[0], rgb.inputs[0])
        ramp = n.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = .12
        ramp.color_ramp.elements[0].color = (.58,.57,.65,1)
        ramp.color_ramp.elements[1].position = .72
        ramp.color_ramp.elements[1].color = (1,1,1,1)
        ramp.color_ramp.interpolation = 'EASE'
        links.new(rgb.outputs['Color'], ramp.inputs[0])
        multiply = n.new('ShaderNodeMixRGB')
        multiply.blend_type = 'MULTIPLY'
        multiply.inputs[0].default_value = 1
        links.new(tex.outputs['Color'], multiply.inputs[1])
        links.new(ramp.outputs['Color'], multiply.inputs[2])
        emit = n.new('ShaderNodeEmission')
        links.new(multiply.outputs[0], emit.inputs['Color'])
        out = n.new('ShaderNodeOutputMaterial')
        if m.name == 'Body_alpha':
            cutoff = n.new('ShaderNodeMath')
            cutoff.operation = 'GREATER_THAN'
            cutoff.inputs[1].default_value = .35
            links.new(tex.outputs['Alpha'], cutoff.inputs[0])
            transparent = n.new('ShaderNodeBsdfTransparent')
            shader_mix = n.new('ShaderNodeMixShader')
            links.new(cutoff.outputs[0], shader_mix.inputs[0])
            links.new(transparent.outputs[0], shader_mix.inputs[1])
            links.new(emit.outputs[0], shader_mix.inputs[2])
            links.new(shader_mix.outputs[0], out.inputs['Surface'])
        else:
            links.new(emit.outputs[0], out.inputs['Surface'])
        m.use_backface_culling = False


def extract_dog_head(original, arm, parent):
    """Make actual head geometry from the provided rig, retaining its UVs."""
    shape(original, 'mouth_smile', .7)
    shape(original, 'eye_happy', .15)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    data = bpy.data.meshes.new_from_object(original.evaluated_get(deps), depsgraph=deps)
    head = bpy.data.objects.new('Dog Sui / supplied Suifel head', data)
    bpy.context.collection.objects.link(head)
    names = {'頭'} | {b.name for b in arm.data.bones['頭'].children_recursive}
    groups = {g.index for g in original.vertex_groups if g.name in names}
    keep = {v.index for v in original.data.vertices
            if sum(g.weight for g in v.groups if g.group in groups) > .5}
    bm = bmesh.new()
    bm.from_mesh(data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context='VERTS')
    bm.to_mesh(data)
    bm.free()
    for v in data.vertices:
        v.co -= Vector((0,0,.79))
    head.parent = parent
    head.location = (0,-.20,.78)
    head.scale = (1.85,1.85,1.85)
    for p in data.polygons:
        p.use_smooth = True
    shape(original, 'mouth_smile', 0)
    shape(original, 'eye_happy', 0)
    return head


def build():
    bpy.ops.wm.open_mainfile(filepath=str(OUT / 'suifel-imported.blend'))
    scene = bpy.context.scene
    main = bpy.data.objects['Suifel']
    main.name = 'Sui / thrower'
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    human = next(o for o in scene.objects if o.type == 'MESH')
    for pb in arm.pose.bones:
        for c in list(pb.constraints):
            pb.constraints.remove(c)
    arm.animation_data_clear()
    if human.data.shape_keys:
        human.data.shape_keys.animation_data_clear()
        for k in human.data.shape_keys.key_blocks:
            k.value = 0
    toon_imported_materials()
    main.scale = (2.15,)*3

    dough = material('Biscuit / warm shortbread', (.73,.40,.12))
    rim = material('Biscuit / browned edge', (.42,.19,.065))
    cocoa = material('Chocolate chips & biscuit eyes', (.15,.055,.035))
    gold = material('Biscuit crown', (1,.67,.13), .38)
    mouth = material('Biscuit / panicked mouth', (.64,.17,.16))
    blush = material('Biscuit / rosy cheeks', (1,.36,.24))
    fur = material('Dog Sui / vanilla plush', (.92,.79,.66))
    ears = material('Dog Sui / floppy berry ears', (.38,.055,.12))
    pawpink = material('Dog Sui / paw pads', (.9,.36,.4))
    black = material('Dog Sui / nose', (.095,.05,.065))
    lilac = material('Pedestal / lavender porcelain', (.39,.25,.57))
    grass = material('Tiny park / pistachio', (.52,.72,.45))
    backdrop = material('Backdrop / peach milk', (.82,.65,.58))
    leaf = material('Leaves / mint', (.20,.49,.36))
    cream = material('Petals / warm cream', (1,.89,.63))
    berry = material('Flowers / berry pink', (.73,.16,.30))

    # The biscuit is a small crowned, fully volumetric character, not a flat card.
    biscuit = empty('Biscuit Sui / frisbee & squash control')
    edge = cylinder('Biscuit / toasted side', (0,0,0), .365, .14, rim, biscuit)
    edge.rotation_euler.x = math.pi/2
    face = cylinder('Biscuit / golden face', (0,-.055,0), .35, .055, dough, biscuit)
    face.rotation_euler.x = math.pi/2
    for i, (x,z,s) in enumerate([(-.23,.17,.07),(.24,.13,.075),(-.21,-.17,.08),(.21,-.22,.055),(.02,.23,.07),(.10,-.08,.04)]):
        chip = sphere(f'Biscuit / chocolate {i}', (x,-.09,z), (s,.015,s*.85), cocoa, biscuit, 20)
        chip.rotation_euler.y = i*.65
    for x in (-.105,.105):
        sphere('Biscuit / dot eye', (x,-.102,.055), (.033,.012,.041), cocoa, biscuit)
        sphere('Biscuit / cheek', (x*1.55,-.10,-.045), (.037,.007,.021), blush, biscuit)
    sphere('Biscuit / cocoa mouth outline', (0,-.104,-.075), (.065,.013,.077), cocoa, biscuit)
    sphere('Biscuit / shouting mouth', (0,-.118,-.075), (.045,.008,.057), mouth, biscuit)
    crown_poly = [(-.15,.33),(-.19,.53),(-.09,.47),(0,.60),(.09,.47),(.19,.53),(.15,.33)]
    verts = [(x,y,z) for y in (-.03,.045) for x,z in crown_poly]
    n = len(crown_poly)
    faces = [tuple(range(n-1,-1,-1)), tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    crown = mesh('Biscuit / little crown', verts, faces, gold, biscuit)
    mod = crown.modifiers.new('Rounded crown', 'BEVEL')
    mod.width, mod.segments = .018, 3
    crown.modifiers.new('Crown normals', 'WEIGHTED_NORMAL')
    for side in (-1,1):
        tube('Biscuit / noodle arm', [(side*.31,0,.03),(side*.44,0,.13),(side*.48,0,.24)], .013, dough, biscuit)
        sphere('Biscuit / mitten', (side*.48,0,.24), (.028,.022,.035), gold, biscuit, 16)
        tube('Biscuit / noodle leg', [(side*.12,0,-.31),(side*.14,0,-.47),(side*.22,0,-.49)], .014, dough, biscuit)

    dog = empty('Dog Sui / run & jump control')
    torso = sphere('Dog Sui / bean-shaped plush body', (0,.16,.49), (.31,.47,.29), fur, dog)
    head = extract_dog_head(human, arm, dog)
    for side in (-1,1):
        ear = sphere('Dog Sui / floppy ear', (side*.30,-.23,.76), (.115,.105,.18), ears, dog)
        ear.rotation_euler.y = side*.45
        sphere('Dog Sui / inner ear', (side*.32,-.313,.72), (.065,.023,.105), pawpink, dog)
    sphere('Dog Sui / small plush muzzle', (0,-.43,.64), (.115,.07,.063), fur, dog)
    sphere('Dog Sui / button nose', (0,-.492,.667), (.034,.025,.024), black, dog, 20)
    collar = cylinder('Dog Sui / berry collar', (0,-.15,.56), .25, .06, ears, dog)
    sphere('Dog Sui / collar bell', (0,-.427,.51), (.045,.025,.045), gold, dog, 20)
    legs = []
    for side in (-1,1):
        for front in (-1,1):
            pivot = empty(f'Dog Sui / leg {side} {front}', (side*.22,front*.28+.1,.40), dog)
            sphere('Dog Sui / plush leg', (0,0,-.13), (.11,.105,.19), fur, pivot)
            sphere('Dog Sui / round paw', (0,-.035,-.28), (.12,.15,.07), fur, pivot)
            sphere('Dog Sui / paw patch', (0,-.13,-.28), (.066,.02,.04), pawpink, pivot)
            legs.append((pivot,side,front))
    tail = empty('Dog Sui / wag control', (0,.54,.63), dog)
    tail_curve = tube('Dog Sui / curled tail', [(0,0,0),(0,.17,.09),(0,.22,.26),(0,.10,.30)], .075, fur, tail)
    tail_curve.data.splines[0].bezier_points[-1].radius = .22

    # A little park on a plinth; open space keeps the flight readable.
    stage = cylinder('Tiny park / lavender plinth', (0,0,-.20), 4.35, .38, lilac)
    stage.scale.y = .63
    top = cylinder('Tiny park / lawn', (0,0,-.01), 4.28, .055, grass)
    top.scale.y = .63
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0,0,-.405))
    bpy.context.object.name = 'Peach studio floor'
    bpy.context.object.data.materials.append(backdrop)
    for x,y,s in [(-3.1,1.35,.8),(-2.0,1.9,.65),(2.9,1.35,.75),(3.45,.65,.5)]:
        cylinder('Park / short trunk', (x,y,.20*s), .06*s, .4*s, dough)
        sphere('Park / round mint tree', (x,y,.57*s), (.27*s,.27*s,.40*s), leaf)
        sphere('Park / mint tree crown', (x-.08*s,y,.83*s), (.19*s,.20*s,.24*s), grass)
    for x,y in [(-3.25,-.6),(-2.6,-1.5),(3.2,-.9),(2.2,-1.7),(.9,1.7),(-.9,1.7)]:
        tube('Park / flower stem', [(x,y,.02),(x,y,.16)], .012, leaf)
        for a in range(5):
            sphere('Park / flower petal', (x+.065*math.cos(a*TAU/5),y+.065*math.sin(a*TAU/5),.18), (.056,.038,.022), cream, segments=16)
        sphere('Park / flower center', (x,y,.19), (.033,.033,.028), gold, segments=16)
    for x,y in [(-3.45,.15),(3.5,-.25)]:
        cylinder('Park / mushroom stem', (x,y,.10), .045,.18,cream)
        sphere('Park / berry mushroom', (x,y,.20), (.13,.13,.055), berry)

    # Catch sparkles appear only for the impact beat.
    sparks = empty('Catch / starburst control')
    for i in range(8):
        a = i*TAU/8
        tube('Catch / gold rays', [(math.cos(a)*.48,0,math.sin(a)*.48),(math.cos(a)*.64,0,math.sin(a)*.64)], .022, gold, sparks)

    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.72,.80,1,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .35
    for name,loc,energy,size,color in [
        ('Large warm key',(-3,-5,8),650,7,(1,.85,.76)),
        ('Soft cool fill',(5,-2,5),450,6,(.76,.85,1)),
        ('Cream rim',(0,5,7),800,5,(1,.85,.67))]:
        bpy.ops.object.light_add(type='AREA', location=loc)
        light = bpy.context.object
        light.name = name
        light.data.energy,light.data.size,light.data.color = energy,size,color
        light.rotation_euler = (Vector((0,0,.8))-light.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.name = 'Camera / animated little theatre'
    cam.data.type = 'ORTHO'
    scene.camera = cam
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.eevee.taa_render_samples = 48
    scene.render.resolution_x,scene.render.resolution_y = 1920,1080
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.compression = 15
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = .35
    scene.view_settings.gamma = 1
    scene.frame_start,scene.frame_end = 1,FPS*SECONDS

    # Keyframes are baked so the blend plays without Python handlers or add-ons.
    release_pos = None
    for frame in range(1,FPS*SECONDS+1):
        t = (frame-1)/FPS
        scene.frame_set(frame)
        final = smooth(10.5,11.3,t)
        pulse = max(0, math.cos(TAU*2*(t-11)))**8 * final
        idle = math.sin(t*TAU*1)*.012
        main.location = (-2.0,0,.015 + idle + pulse*.08)
        main.rotation_euler = (0, .025*math.sin(t*2), .12 + .08*math.sin(t*1.1))
        main.scale = (2.15*(1+.13*pulse),2.15*(1+.08*pulse),2.15*(1-.22*pulse))
        wind = smooth(1.7,2.8,t)*(1-smooth(3.05,3.5,t))
        swing = smooth(3.05,3.5,t)*(1-smooth(3.7,4.6,t))
        protest = smooth(8.4,9.2,t)*(1-smooth(10.5,11.5,t))
        pose(arm,'左腕',(0,38-45*wind-68*swing-20*final,70*wind-25*swing),frame)
        pose(arm,'左ひじ',(-15*wind,-65*wind-10*swing-20*final,0),frame)
        pose(arm,'右腕',(0,-40+45*protest+20*final,0),frame)
        pose(arm,'右ひじ',(0,60*protest+20*final,0),frame)
        pose(arm,'上半身',(2*wind,0,-12*wind+8*swing+3*math.sin(t*3)*final),frame)
        pose(arm,'頭',(0,0,-7*protest+4*math.sin(t*4)*final),frame)
        shape(human,'mouth_o',.75*smooth(5.1,5.7,t)*(1-smooth(7.7,8.3,t)),frame)
        shape(human,'mouth_∧',.5*protest,frame)
        shape(human,'mouth_smile',.5*(1-protest)*(1-smooth(5.0,5.6,t))+.6*final,frame)
        shape(human,'eye_surprise',.6*smooth(5.1,5.7,t)*(1-smooth(7.7,8.3,t)),frame)
        shape(human,'eye_open',.55*smooth(5.1,5.7,t)*(1-smooth(7.7,8.3,t)),frame)
        shape(human,'eye_angry',.55*protest,frame)
        shape(human,'eye_happy',.3*final,frame)
        blink = sum(math.exp(-((t-c)/.07)**2) for c in (.9,4.4,7.5,10.2,13.1,15.1))
        shape(human,'eye_close',min(1,blink),frame)
        set_keys(main,frame)

        # Puppy accelerates, takes off, catches at 5.5 s, lands and trots back.
        run = smooth(3.6,5.5,t)
        back = smooth(6.3,8.8,t)
        dx = mix(1.15,2.5,run)
        dx = mix(dx,-.15,back)
        jumpu = max(0,min(1,(t-4.6)/1.8))
        jump = .86*math.sin(math.pi*jumpu) if 4.6<t<6.4 else 0
        moving = (smooth(3.5,3.8,t)*(1-smooth(5.35,5.6,t)) + smooth(6.3,6.5,t)*(1-smooth(8.5,8.8,t)))
        trot = .06*abs(math.sin(t*TAU*3))*moving
        dog.location = (dx,-.10,jump+trot+.02+.05*pulse)
        angle = mix(.30,1.05,run)
        angle = mix(angle,-.80,smooth(6.4,6.9,t))
        angle = mix(angle,.04,smooth(8.6,9.5,t))
        dog.rotation_euler = (.09*math.sin(t*TAU*3)*moving,0,angle)
        dog.scale = (1+.16*pulse,1+.10*pulse,1-.23*pulse)
        set_keys(dog,frame)
        for leg,side,front in legs:
            leg.rotation_euler.x = .48*math.sin(t*TAU*3+(0 if side==front else math.pi))*moving
            leg.rotation_euler.y = side*.08*jump
            set_keys(leg,frame,('rotation_euler',))
        head.rotation_euler = (.025*math.sin(t*4), .04*math.sin(t*5), .04*math.sin(t*3))
        set_keys(head,frame,('rotation_euler',))
        tail.rotation_euler.y = .7*math.sin(t*TAU*4)
        set_keys(tail,frame,('rotation_euler',))
        bpy.context.view_layer.update()

        if t < 3.5:
            wrist = arm.pose.bones['左手首']
            palm = wrist.matrix @ wrist.bone.matrix_local.inverted() @ Vector((.302,-.05,.485))
            biscuit.location = arm.matrix_world @ palm + Vector((.13,-.035,.08))
            biscuit.rotation_euler = (.12, -.15, -.15+.10*math.sin(t*4))
            release_pos = biscuit.location.copy()
        elif t < 5.5:
            u = (t-3.5)/2
            # Fixed endpoint equals the puppy's bite position at its jump apex.
            catch = Vector((2.5 + .27*math.cos(1.05)+math.sin(1.05)*.60,
                            -.10+.27*math.sin(1.05)-math.cos(1.05)*.60, .02+.86+.34))
            biscuit.location = release_pos.lerp(catch,u)
            biscuit.location.z += .65*math.sin(math.pi*u)
            biscuit.rotation_euler = (.25+.85*math.sin(math.pi*u), TAU*2*u, -.2)
        else:
            biscuit.location = dog.matrix_world @ Vector((.27,-.60,.34))
            biscuit.rotation_euler = (dog.rotation_euler.x+.08*math.sin(t*6),0,dog.rotation_euler.z)
        biscuit.scale = (.82*(1+.22*pulse),.82*(1+.10*pulse),.82*(1-.20*pulse))
        set_keys(biscuit,frame)
        sparks.location = biscuit.location
        pop = math.sin(math.pi*max(0,min(1,(t-5.45)/.45))) if 5.45<t<5.9 else 0
        sparks.scale = (pop,)*3
        sparks.rotation_euler.z = -.1
        set_keys(sparks,frame)

        # Slow camera moves retain the complete action and generous title space.
        follow = smooth(3.4,4.6,t)*(1-smooth(6.7,8.7,t))
        ending = smooth(9.5,11.5,t)
        target = Vector((.08+.6*follow-.55*ending,0,1.0+.15*follow))
        cam.location = target + Vector((3.0,-10.5,5.0))
        cam.rotation_euler = (target-cam.location).to_track_quat('-Z','Y').to_euler()
        cam.data.ortho_scale = 8.8-.45*follow-.8*ending
        set_keys(cam,frame,('location','rotation_euler'))
        cam.data.keyframe_insert(data_path='ortho_scale',frame=frame)

    for sec,label in [(0,'01 / Biscuit is the frisbee'),(1.7,'02 / Wind up'),(3.5,'03 / Throw'),(5.5,'04 / Catch'),(6.4,'05 / Return'),(9,'06 / Not dinner'),(11,'07 / Squash on the beat')]:
        scene.timeline_markers.new(label,frame=round(sec*FPS)+1)
    scene['short_title'] = '饼干岁飞盘大会'
    scene['model_credit'] = 'Suifel by Yora; based on Kipfel'
    scene['animation_fps'] = FPS
    scene['music_bpm'] = 120
    scene['story'] = 'Throw / puppy leap / catch / return / squish together'
    music_path = OUT / 'original-biscuit-beat.wav'
    if music_path.is_file():
        editor = scene.sequence_editor_create()
        strip = editor.strips.new_sound('Original 120 BPM biscuit beat',str(music_path),channel=1,frame_start=1)
        if hasattr(strip.sound, 'pack'):
            strip.sound.pack()
        scene.sync_mode = 'AUDIO_SYNC'
        # Image rendering remains the active 3D camera; the sound plays in the editor.
        scene.render.use_sequencer = False
    # All assets are packed; no import plugin is needed to play this scene.
    for image in bpy.data.images:
        if image.source == 'FILE' and image.has_data and not image.packed_file:
            image.pack()
    scene.frame_set(1)
    scene.render.filepath = str(OUT / 'frames/frame_')
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'sui-frisbee.blend'), compress=True)
    report = {'frames':scene.frame_end,'fps':FPS,'seconds':SECONDS,
              'resolution':[scene.render.resolution_x,scene.render.resolution_y],
              'meshes':len([o for o in scene.objects if o.type=='MESH']),
              'objects':len(scene.objects),'packed_images':len([i for i in bpy.data.images if i.packed_file]),
              'head_vertices':len(head.data.vertices),'source_model':str(OUT/'suifel-imported.blend')}
    (OUT/'scene-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print('SCENE_REPORT',json.dumps(report))
    return scene


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    scene = build()
    if args.preview:
        scene.render.resolution_percentage = 67
        for frame in (1,66,88,119,133,156,204,265,277,301,384):
            scene.frame_set(frame)
            scene.render.filepath = str(OUT/f'previews/frame_{frame:04d}.png')
            bpy.ops.render.render(write_still=True)
    if args.render:
        (OUT/'frames').mkdir(exist_ok=True)
        bpy.ops.render.render(animation=True)


if __name__ == '__main__':
    main()
