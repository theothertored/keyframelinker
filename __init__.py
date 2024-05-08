from __future__ import annotations
from bpy.app.handlers import persistent
import bpy
import typing

bl_info = {
    "name": "Keyframe Linker",
    "author": "Tored",
    "blender": (3, 4, 1),
    "category": "Animation"
}

CPROP_LINKED_FRAMES = 'linked_frames'

class LinkedFrame:
    number: int
    flipped: bool

    def __init__(self, number: int, flipped: bool = False) -> None:
        self.number = number
        self.flipped = flipped

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, LinkedFrame) and __o.number == self.number

    def __hash__(self) -> int:
        return self.number


def get_frame_sets_for_action(action: bpy.types.Action) -> list[set[LinkedFrame]]:
    prop = action.get(CPROP_LINKED_FRAMES, [])
    frame_sets = []
    for sublist in prop:
        frame_set = set()
        for entry in sublist:
            frame_set.add(LinkedFrame(entry[0], bool(entry[1])))
        
        frame_sets.append(frame_set)

    return frame_sets
        
    
def set_frame_sets_for_action(action: bpy.types.Action, frame_sets: list[set[LinkedFrame]]):
    prop_val = [[(f.number, f.flipped) for f in frame_set] for frame_set in frame_sets if len(frame_set) > 1]
    if len(prop_val) == 0:
        # print('no frame sets to save.')
        if CPROP_LINKED_FRAMES in action:
            # print('deleting custom property.')
            del action[CPROP_LINKED_FRAMES]
    else:
        # print('saving frame sets:')
        # print(prop_val)
        action[CPROP_LINKED_FRAMES] = prop_val

    
def find_linked_frame_set(frame_sets: list[set[LinkedFrame]], frame_number):
    return next((frame_set for frame_set in frame_sets if any(frame.number == frame_number for frame in frame_set)), None)

def find_linked_frame_sets(frame_sets: list[set[LinkedFrame]], frame_numbers):
    return [frame_set for frame_set in frame_sets if any(frame.number in frame_numbers for frame in frame_set)]

def find_selected_frame_numbers(action: bpy.types.Action):
    frame_numbers: set[int] = set()

    for fcurve in action.fcurves:
        for kf in fcurve.keyframe_points:
            if kf.select_control_point:
                frame_numbers.add(int(kf.co.x))

    return frame_numbers

def remove_all_in_place(predicate, l):
    i = 0
    while i < len(l):
        if predicate(l[i]):
            del l[i]
        else:
            i += 1

def remove_all_from_frame_set(frame_set: set[LinkedFrame], frame_numbers):
    for number in frame_numbers:
        f = LinkedFrame(number)
        if f in frame_set:
            frame_set.remove(f)


class LinkFrames(bpy.types.Operator):
    """Links frames - when one of them is edited, they all change."""
    bl_idname = "keyframes.link_frames"
    bl_label = "Link Frames"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        
        action = context.object.animation_data.action
        frame_sets = get_frame_sets_for_action(action)
        
        frame_numbers_to_link = find_selected_frame_numbers(action)

        if len(frame_numbers_to_link) > 0:

            found_sets = find_linked_frame_sets(frame_sets, frame_numbers_to_link)

            if len(found_sets) == 0:
                # no frames in the set are linked to any other frames, create new set
                frame_set = set()
                
                flip = False
                for frame_number in sorted(frame_numbers_to_link):
                    frame_set.add(LinkedFrame(frame_number, flip))
                    flip = not flip

                frame_sets.append(frame_set)

            elif len(found_sets) == 1:
                # some frames in the set are in one set, add unlinked frames to that set
                frame_set = found_sets[0]
                for frame_number in frame_numbers_to_link:
                    frame_set.add(LinkedFrame(frame_number))
                    
            else:
                # frames are in two or more sets, create an union of all involved sets
                union_set = set()

                for found_set in found_sets:
                    union_set = union_set.union(found_set)
                    frame_sets.remove(found_set)

                for frame_number in frame_numbers_to_link:
                    union_set.add(LinkedFrame(frame_number))
                
                frame_sets.append(union_set)
                

            set_frame_sets_for_action(action, frame_sets)

            # make sure the UI actually updates
            context.view_layer.update()
            refresh_keyframe_areas(context)

            LinkedFrameInfo.execute(self, context)


        return {'FINISHED'}


class FlipLinkedFrame(bpy.types.Operator):
    """Flips a linked frame - this one will be pasted flipped."""
    bl_idname = "keyframes.flip_linked_frames"
    bl_label = "Flip Linked Frames"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):

        action = context.object.animation_data.action
        frame_sets = get_frame_sets_for_action(action)
        
        frame_numbers_to_flip = find_selected_frame_numbers(action)

        if len(frame_numbers_to_flip) == 0:
            frame_numbers_to_flip = {context.scene.frame_current}

        flip_count = 0

        for frame_number in frame_numbers_to_flip:
            frame_set = find_linked_frame_set(frame_sets, frame_number)

            if frame_set:
                for frame in frame_set:
                    if frame.number == frame_number:
                        frame.flipped = not frame.flipped
                        flip_count += 1
                        break

        if flip_count > 0:
            set_frame_sets_for_action(action, frame_sets)
            LinkedFrameInfo.execute(self, context)

        return {'FINISHED'}


class UnlinkFrames(bpy.types.Operator):
    """Unlinks frames that were linked by using LinkFrames."""
    bl_idname = "keyframes.unlink_frames"
    bl_label = "Unlink Frames"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):

        action = context.object.animation_data.action
        frame_sets = get_frame_sets_for_action(action)
        
        frame_numbers_to_unlink = find_selected_frame_numbers(action)

        if len(frame_numbers_to_unlink) == 0:
            frame_numbers_to_unlink = {context.scene.frame_current}

        found_sets = find_linked_frame_sets(frame_sets, frame_numbers_to_unlink)

        if len(found_sets) > 0:

            for frame_set in found_sets:
                remove_all_from_frame_set(frame_set, frame_numbers_to_unlink)

            # remove empty sets
            remove_all_in_place(lambda s: len(s) <= 1, frame_sets)

            set_frame_sets_for_action(action, frame_sets)

            # make sure the UI actually updates
            context.view_layer.update()
            refresh_keyframe_areas(context)

            LinkedFrameInfo.execute(self, context)

        return {'FINISHED'}


class LinkedFrameInfo(bpy.types.Operator):
    """Prints information about linked frames for the current action to the Info editor."""
    bl_idname = "keyframes.linked_frame_info"
    bl_label = "Linked Frame Info"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        
        action = context.object.animation_data.action
        frame_sets = get_frame_sets_for_action(action)
        
        if len(frame_sets) > 0:
            i = 1
            for frame_set in frame_sets:
                s = (', ').join(f'{f.number}{" F" if f.flipped else ""}' for f in sorted(frame_set, key = lambda f: f.number))
                self.report({'INFO'}, f'set {str(i).rjust(2, "0")}: {s}')
                i += 1
        else:
            self.report({'INFO'}, f'no linked frames for this action.')
            

        return {'FINISHED'}


def refresh_keyframe_areas(context: bpy.types.Context):
    for area in context.screen.areas:
        if area.type in ('DOPESHEET_EDITOR', 'GRAPH_EDITOR', 'NLA_EDITOR'):
            area.tag_redraw()


@persistent
def save_pre_handler(scene: bpy.types.Scene):

    area_kf = next(a for a in bpy.context.screen.areas if a.type in ('DOPESHEET_EDITOR', 'GRAPH_EDITOR'))

    if not area_kf:
        raise RuntimeError('Could not find a dopesheet editor or graph editor to resolve linked keyframes.')

    selected_bones_before = [bone for bone in bpy.context.selected_pose_bones_from_active_object]
    active_pose_bone = bpy.context.active_pose_bone

    # do things in dope sheet/graph editor
    with bpy.context.temp_override(
        window=bpy.context.window,
        area=area_kf,
        regions=[region for region in area_kf.regions if region.type == 'WINDOW'][0],
        screen=bpy.context.window.screen
    ):
        action = bpy.context.object.animation_data.action

        if not action: return

        frame_sets = get_frame_sets_for_action(action)
        current_frame_number = bpy.context.scene.frame_current

        if not frame_sets: return

        frame_set = find_linked_frame_set(frame_sets, current_frame_number)

        if not frame_set: return

        current_frame = next(f for f in frame_set if f.number == current_frame_number)

        old_area_type = area_kf.type
        area_kf.type = 'DOPESHEET_EDITOR'

        bpy.ops.pose.select_all(action = 'SELECT')

        bpy.ops.action.select_all(action = 'DESELECT')
        bpy.ops.action.select_column(mode = 'CFRA')

        bpy.ops.action.copy()
        
        for linked_frame in frame_set:

            if linked_frame.number == current_frame_number:
                continue

            bpy.context.scene.frame_set(linked_frame.number)
            bpy.ops.action.paste(flipped = current_frame.flipped != linked_frame.flipped)
            print(f'copied action from {current_frame_number} to {linked_frame.number}{" (flipped)" if current_frame.flipped != linked_frame.flipped else ""}')

        bpy.ops.action.select_all(action = 'DESELECT')

        bpy.context.scene.frame_set(current_frame_number)
        bpy.ops.pose.copy()

        for linked_frame in frame_set:

            if linked_frame.number == current_frame_number:
                continue

            bpy.context.scene.frame_set(linked_frame.number)
            bpy.ops.pose.paste(flipped = current_frame.flipped != linked_frame.flipped)
            print(f'copied pose from {current_frame_number} to {linked_frame.number}{" (flipped)" if current_frame.flipped != linked_frame.flipped else ""}')

        bpy.context.scene.frame_set(current_frame_number)

        # restore bone selection

        bpy.ops.pose.select_all(action = 'DESELECT')

        for bone in selected_bones_before:
            bone.bone.select = True
        
        if active_pose_bone:
            active_pose_bone.bone.select = True

        bpy.context.view_layer.update()

        area_kf.type = old_area_type

        # make sure the UI actually updates
        refresh_keyframe_areas(bpy.context)

        

operators_to_register = [
    LinkFrames, 
    FlipLinkedFrame, 
    UnlinkFrames,
    LinkedFrameInfo
]

parent_menus = [
    bpy.types.DOPESHEET_MT_key, 
    bpy.types.GRAPH_MT_key
]


def menu_func(self: bpy.types.Menu, context):
    self.layout.separator()
    for op in operators_to_register:
        self.layout.operator(op.bl_idname)


def register():
    for op in operators_to_register:
        bpy.utils.register_class(op)

    bpy.app.handlers.save_pre.append(save_pre_handler)

    for menu in parent_menus:
        menu.append(menu_func)

    print('keyframelinker registered')


def unregister():

    for op in operators_to_register:
        bpy.utils.unregister_class(op)

    bpy.app.handlers.save_pre.remove(save_pre_handler)

    for menu in parent_menus:
        menu.remove(menu_func)
        
    print('keyframelinker unregistered')
