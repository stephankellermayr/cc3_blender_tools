# Copyright (C) 2021 Victor Soupday
# This file is part of CC3_Blender_Tools <https://github.com/soupday/cc3_blender_tools>
#
# CC3_Blender_Tools is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# CC3_Blender_Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with CC3_Blender_Tools.  If not, see <https://www.gnu.org/licenses/>.

import bpy

from . import materials, modifiers, nodeutils, utils, vars

def add_object_to_character(chr_cache, obj : bpy.types.Object):
    props = bpy.context.scene.CC3ImportProps

    if chr_cache and obj and obj.type == "MESH":

        # convert the object name to remove any duplicate suffixes:
        obj_name = utils.unique_object_name(obj.name, obj)
        if obj.name != obj_name:
            obj.name = obj_name

        # add the object into the object cache
        obj_cache = chr_cache.add_object_cache(obj)
        obj_cache.object_type = "DEFAULT"
        obj_cache.user_added = True

        add_missing_materials_to_character(chr_cache, obj, obj_cache)

        utils.clear_selected_objects()

        # clear any parenting
        if obj.parent:
            if utils.set_active_object(obj):
                    bpy.ops.object.parent_clear(type = "CLEAR_KEEP_TRANSFORM")

        # parent to character
        arm = chr_cache.get_armature()
        if arm:
            if utils.try_select_objects([arm, obj]):
                if utils.set_active_object(arm):
                    bpy.ops.object.parent_set(type = "OBJECT", keep_transform = True)

                    # add or update armature modifier
                    arm_mod : bpy.types.ArmatureModifier = modifiers.get_armature_modifier(obj, True)
                    if arm_mod:
                        modifiers.move_mod_first(obj, arm_mod)
                        arm_mod.object = arm

                    utils.clear_selected_objects()
                    utils.set_active_object(obj)


def clean_up_character_data(chr_cache):

    props = bpy.context.scene.CC3ImportProps

    mats = []
    objects = []
    arm = chr_cache.get_armature()

    if arm:

        for obj in arm.children:
            if obj and obj.type == "MESH":
                if len(obj.users_scene) > 0:
                    objects.append(obj)
                    for mat in obj.data.materials:
                        if mat and mat not in mats:
                            mats.append(mat)

        delete_mats = []
        delete_objects = []

        cache_mats = chr_cache.get_all_materials()
        cache_objects = chr_cache.get_all_objects(False)

        for obj in cache_objects:
            if obj and obj not in objects:
                delete_objects.append(obj)

        for mat in cache_mats:
            if mat and mat not in mats:
                delete_mats.append(mat)

        for obj in delete_objects:
            chr_cache.remove_object_cache(obj)

        for mat in delete_mats:
            chr_cache.remove_mat_cache(mat)


def character_data_needs_clean_up(chr_cache):

    props = bpy.context.scene.CC3ImportProps

    if chr_cache:

        mats = []
        objects = []
        arm = chr_cache.get_armature()

        if arm:

            for obj in arm.children:
                if obj and obj.type == "MESH":
                    if len(obj.users_scene) > 0:
                        objects.append(obj)
                        for mat in obj.data.materials:
                            if mat and mat not in mats:
                                mats.append(mat)

            cache_objects = chr_cache.get_all_objects(False)

            if len(cache_objects) > len(objects):
                return True

            cache_mats = chr_cache.get_all_materials()

            if len(cache_mats) > len(mats):
                return True

    return False


def add_missing_materials_to_character(chr_cache, obj, obj_cache):
    props  = bpy.context.scene.CC3ImportProps

    if chr_cache and obj and obj_cache and obj.type == "MESH":

        obj_name = obj.name

        # add a default material if none exists...
        if len(obj.data.materials) == 0:
            mat_name = utils.unique_material_name(obj_name)
            mat = bpy.data.materials.new(mat_name)
            obj.data.materials.append(mat)

        for mat in obj.data.materials:
            if mat:
                mat_cache = chr_cache.get_material_cache(mat)

                if not mat_cache:
                    add_material_to_character(chr_cache, obj, obj_cache, mat)


def add_material_to_character(chr_cache, obj, obj_cache, mat):
    props = bpy.context.scene.CC3ImportProps

    if chr_cache and obj and obj_cache and mat:

        # convert the material name to remove any duplicate suffixes:
        mat_name = utils.unique_material_name(mat.name, mat)
        if mat.name != mat_name:
            mat.name = mat_name

        # make sure there are nodes:
        if not mat.use_nodes:
            mat.use_nodes = True

        # add the material into the material cache
        mat_cache = chr_cache.add_material_cache(mat, "DEFAULT")
        mat_cache.user_added = True

        # convert any existing PrincipledBSDF based material to a rl_pbr shader material
        # can treat existing textures as embedded textures, so they will be picked up by the material builder.
        materials.detect_embedded_textures(chr_cache, obj, obj_cache, mat, mat_cache)
        # finally connect up the pbr shader...
        #shaders.connect_pbr_shader(obj, mat, None)
        convert_to_rl_pbr(mat)


def convert_to_rl_pbr(mat):
    shader_group = "rl_pbr_shader"
    shader_name = "rl_pbr_shader"
    shader_id = "(" + str(shader_name) + ")"
    bsdf_id = "(" + str(shader_name) + "_BSDF)"

    group_node: bpy.types.Node = None
    bsdf_node: bpy.types.Node = None
    output_node: bpy.types.Node = None
    gltf_node: bpy.types.Node = None
    too_complex = False

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    n : bpy.types.ShaderNode
    for n in nodes:

        if n.type == "BSDF_PRINCIPLED":

            if not bsdf_node:
                utils.log_info("Found BSDF: " + n.name)
                bsdf_node = n
            else:
                too_complex = True

        elif n.type == "GROUP" and n.node_tree and shader_name in n.name and vars.VERSION_STRING in n.node_tree.name:

            if not group_node:
                utils.log_info("Found Shader Node: " + n.name)
                group_node = n
            else:
                too_complex = True

        elif n.type == "GROUP" and n.node_tree and "glTF Settings" in n.node_tree.name:

            if not gltf_node:
                gltf_node = n
            else:
                too_complex = True

        elif n.type == "OUTPUT_MATERIAL":

            if output_node:
                nodes.remove(n)
            else:
                output_node = n

    if too_complex:
        utils.log_warn(f"Material {mat.name} is too complex to convert!")
        return

    # move all the nodes back to accomodate the group shader node
    for n in nodes:
        loc = n.location
        n.location = [loc[0] - 600, loc[1]]

    # make group node if none
    # ensure correct names so find_shader_nodes can find them
    if not group_node:
        group = nodeutils.get_node_group(shader_group)
        group_node = nodes.new("ShaderNodeGroup")
        group_node.node_tree = group
    group_node.name = utils.unique_name(shader_id)
    group_node.label = "Pbr Shader"
    group_node.width = 240
    group_node.location = (-400, 0)

    # make bsdf node if none
    if not bsdf_node:
        bsdf_node = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf_node.name = utils.unique_name(bsdf_id)
    bsdf_node.label = "Pbr Shader"
    bsdf_node.width = 240
    bsdf_node.location = (200, 400)

    # make output node if none
    if not output_node:
        output_node = nodes.new("ShaderNodeOutputMaterial")
    output_node.location = (900, -400)

    # remap bsdf socket inputs to shader group node sockets
    sockets = [
        ["Base Color", "BSDF", "Diffuse Map"],
        ["Metallic", "BSDF", "Metallic Map"],
        ["Specular", "BSDF", "Specular Map"],
        ["Roughness", "BSDF", "Roughness Map"],
        ["Emission", "BSDF", "Emission Map"],
        ["Alpha", "BSDF", "Alpha Map"],
        ["Normal:Color", "BSDF", "Normal Map"], # normal image > normal map (Color) > BSDF (Normal)
        ["Normal:Normal:Color", "BSDF", "Normal Map"], # normal image > normal map (Color) > bump map (Normal) > BSDF (Normal)
        ["Normal:Height", "BSDF", "Bump Map"], # bump image > bump map (Height) > BSDF (Normal)
        ["Occlusion", "GLTF", "AO Map"]
    ]
    socket_mapping = {}
    for socket_trace, node_type, group_socket in sockets:
        if node_type == "BSDF":
            n = bsdf_node
        elif node_type == "GLTF":
            n = gltf_node
        else:
            n = None
        if n:
            linked_node, linked_socket = nodeutils.trace_input_sockets(n, socket_trace)
            if linked_node and linked_socket:
                if linked_node != group_node:
                    socket_mapping[group_socket] = [linked_node, linked_socket]

    # connect the shader group node sockets
    for socket_name in socket_mapping:
        linked_info = socket_mapping[socket_name]
        linked_node = linked_info[0]
        linked_socket = linked_info[1]
        nodeutils.link_nodes(links, linked_node, linked_socket, group_node, socket_name)

    # connect all group_node outputs to BSDF inputs:
    for socket in group_node.outputs:
        nodeutils.link_nodes(links, group_node, socket.name, bsdf_node, socket.name)

    # connect bsdf to output node
    nodeutils.link_nodes(links, bsdf_node, "BSDF", output_node, "Surface")

    # connect the displacement to the output
    nodeutils.link_nodes(links, group_node, "Displacement", output_node, "Displacement")

    return


def transfer_skin_weights(chr_cache, objects):
    body = None
    for obj_cache in chr_cache.object_cache:
        if obj_cache.object_type == "BODY":
            body = obj_cache.object

    if not body:
        return

    if body in objects:
        objects.remove(body)

    selected = bpy.context.selected_objects.copy()

    for obj in objects:
        if obj.type == "MESH":
            if (utils.clear_selected_objects() and
                utils.try_select_object(body) and
                utils.set_active_object(obj)):
                bpy.ops.object.data_transfer(use_reverse_transfer=True,
                                            data_type='VGROUP_WEIGHTS',
                                            use_create=True,
                                            vert_mapping='POLYINTERP_NEAREST',
                                            use_object_transform=True,
                                            layers_select_src='NAME',
                                            layers_select_dst='ALL',
                                            mix_mode='REPLACE')

    utils.clear_selected_objects()
    utils.try_select_objects(selected)


class CC3OperatorCharacter(bpy.types.Operator):
    """CC3 Character Functions"""
    bl_idname = "cc3.character"
    bl_label = "Character Functions"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    param: bpy.props.StringProperty(
            name = "param",
            default = ""
        )

    def execute(self, context):
        props = bpy.context.scene.CC3ImportProps

        if self.param == "ADD_PBR":
            chr_cache = props.get_context_character_cache(context)
            obj = context.active_object
            add_object_to_character(chr_cache, obj)

        elif self.param == "ADD_MATERIALS":
            chr_cache = props.get_context_character_cache(context)
            obj = context.active_object
            obj_cache = chr_cache.get_object_cache(obj)
            add_missing_materials_to_character(chr_cache, obj, obj_cache)

        elif self.param == "CLEAN_UP_DATA":
            chr_cache = props.get_context_character_cache(context)
            obj = context.active_object
            clean_up_character_data(chr_cache)

        elif self.param == "TRANSFER_WEIGHTS":
            chr_cache = props.get_context_character_cache(context)
            objects = bpy.context.selected_objects
            transfer_skin_weights(chr_cache, objects)

        return {"FINISHED"}

    @classmethod
    def description(cls, context, properties):

        if properties.param == "ADD_PBR":
            return "Add object to the character with pbr materials"
        elif properties.param == "ADD_MATERIALS":
            return "Add any new materials to the character data that are in this object but not in the character data"
        elif properties.param == "CLEAN_UP_DATA":
            return "Remove any objects from the character data that are no longer part of the character and remove any materials from the character that are no longer in the character objects"
        elif properties.param == "TRANSFER_WEIGHTS":
            return "Transfer skin weights from the character body to the selected objects"
        return ""
