from __future__ import division

import math
import numpy

from OpenGL.GL import *
from OpenGL.GLE import *
from OpenGL.GLUT import *
from OpenGL.arrays.vbo import VBO


def line_slope(a, b):
    slope = (b.y - a.y) / (b.x - a.x)
    return slope

def compile_display_list(func, *options):
    display_list = glGenLists(1)
    glNewList(display_list, GL_COMPILE)
    func(*options)
    glEndList()
    return display_list


class Platform(object):
    # makerbot platform size
    width = 120
    depth = 100
    grid  = 10

    def __init__(self):
        self.color_guides = (0xaf / 255, 0xdf / 255, 0x5f / 255, 0.4)
        self.color_fill   = (0xaf / 255, 0xdf / 255, 0x5f / 255, 0.1)
        self.initialized = False

    def init(self):
        self.display_list = compile_display_list(self.draw)
        self.initialized = True

    def draw(self):
        glPushMatrix()

        glTranslate(-self.width / 2, -self.depth / 2, 0)
        glColor(*self.color_guides)

        # draw the grid
        glBegin(GL_LINES)
        for i in range(0, self.width + self.grid, self.grid):
            glVertex3f(float(i), 0.0,        0.0)
            glVertex3f(float(i), self.depth, 0.0)

        for i in range(0, self.depth + self.grid, self.grid):
            glVertex3f(0,          float(i), 0.0)
            glVertex3f(self.width, float(i), 0.0)
        glEnd()

        # draw fill
        glColor(*self.color_fill)
        glRectf(0.0, 0.0, float(self.width), float(self.depth))

        glPopMatrix()

    def display(self):
        glCallList(self.display_list)


class GcodeModel(object):
    def __init__(self, layers):
        self.layers = layers
        self.max_layers = len(self.layers)
        self.num_layers_to_draw = self.max_layers
        self.arrows_enabled = True
        self.initialized = False

        self.colors = {
            'red':    (1.0, 0.0, 0.0, 0.6),
            'yellow': (1.0, 0.875, 0.0, 0.6),
            'orange': (1.0, 0.373, 0.0, 0.6),
            'green':  (0.0, 1.0, 0.0, 0.6),
            'cyan':   (0.0, 0.875, 0.875, 0.6),
            'gray':   (0.5, 0.5, 0.5, 0.5),
        }

        line_count = 0
        for layer in self.layers:
            line_count += len(layer)
        print '!!! line count:     ', line_count
        print '!!! lines per layer:', round(line_count / self.max_layers)

    def init(self):
        """
        Create a display list for each model layer.
        """
        self.display_lists = self.draw_layers()

        self.arrow_lists = []
        if self.arrows_enabled:
            for layer in self.layers:
                self.draw_arrows(layer, self.arrow_lists)

        self.initialized = True

    def draw_layers(self, list_container=None):
        if list_container is None:
            list_container = []

        for layer_no, layer in enumerate(self.layers):
            layer_list = compile_display_list(self.draw_layer,
                layer, (layer_no == self.num_layers_to_draw - 1))
            list_container.append(layer_list)

        return list_container

    def draw_layer(self, layer, last=False):
        glPushMatrix()
        glBegin(GL_LINES)

        for movement in layer:
            point_a, point_b = movement.points()

            glColor(*self.movement_color(movement))
            glVertex3f(point_a.x, point_a.y, point_a.z)
            glVertex3f(point_b.x, point_b.y, point_b.z)

        glEnd()
        glPopMatrix()

    def draw_arrows(self, layer, list_container=None):
        if list_container is None:
            list_container = []

        layer_arrow_list = compile_display_list(self._draw_arrows, layer)
        list_container.append(layer_arrow_list)

        return list_container

    def _draw_arrows(self, layer):
        for movement in layer:
            self.draw_arrow(movement)

    def draw_arrow(self, movement):
        a, b = movement.points()
        angle = self.points_angle(a, b)

        glPushMatrix()

        glTranslate(b.x, b.y, b.z)
        glRotate(angle, 0.0, 0.0, 1.0)
        glColor(*self.movement_color(movement))

        glBegin(GL_TRIANGLES)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.4, -0.2, 0.0)
        glVertex3f(0.4, 0.2, 0.0)
        glEnd()

        glPopMatrix()

    def movement_color(self, movement):
        if not movement.extruder_on:
            color = self.colors['gray']
        elif movement.is_loop:
            color = self.colors['yellow']
        elif movement.is_perimeter and movement.is_perimeter_outer:
            color = self.colors['cyan']
        elif movement.is_perimeter:
            color = self.colors['green']
        else:
            color = self.colors['red']

        return color

    def points_angle(self, a, b):
        try:
            slope = line_slope(a, b)
            angle = math.degrees(math.atan(slope))
            if b.x > a.x:
                angle = 180 + angle
        except ZeroDivisionError:
            angle = 90
            if b.y > a.y:
                angle = 180 + angle

        return angle

    def display(self):
        for layer in self.display_lists[:self.num_layers_to_draw]:
            glCallList(layer)

        if self.arrows_enabled:
            glCallList(self.arrow_lists[self.num_layers_to_draw - 1])


class StlModel(object):
    def __init__(self, data):
        vertices, normals = data
        # convert python lists to numpy arrays for constructing vbos
        self.vertices = numpy.require(vertices, 'f')
        self.normals  = numpy.require(normals, 'f')

        self.display_list = None

        self.mat_specular = (1.0, 1.0, 1.0, 1.0)
        self.mat_shininess = 50.0
        self.light_position = (20.0, 20.0, 20.0)
        self.scaling_factor = 1.0

        self.max_layers = 42

        self.initialized = False

    def init(self):
        """
        Create vertex buffer objects (VBOs).
        """
        self.vertex_buffer = VBO(self.vertices, 'GL_STATIC_DRAW')
        self.normal_buffer = VBO(self.normals, 'GL_STATIC_DRAW')
        self.initialized = True

    def draw_facets(self):
        glPushMatrix()

        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glShadeModel(GL_SMOOTH)

        # material properties (white plastic)
        glMaterial(GL_FRONT, GL_AMBIENT, (0.0, 0.0, 0.0, 1.0))
        glMaterial(GL_FRONT, GL_DIFFUSE, (0.55, 0.55, 0.55, 1.0))
        glMaterial(GL_FRONT, GL_SPECULAR, (0.7, 0.7, 0.7, 1.0))
        glMaterial(GL_FRONT, GL_SHININESS, 32.0)

        # lights properties
        glLight(GL_LIGHT0, GL_AMBIENT, (0.3, 0.3, 0.3, 1.0))
        glLight(GL_LIGHT0, GL_DIFFUSE, (0.3, 0.3, 0.3, 1.0))
        glLight(GL_LIGHT1, GL_DIFFUSE, (0.3, 0.3, 0.3, 1.0))

        # lights position
        glLightfv(GL_LIGHT0, GL_POSITION, self.light_position)
        glLightfv(GL_LIGHT1, GL_POSITION, (-20.0, -20.0, 20.0))

        glColor(1.0, 1.0, 1.0)

        ### VBO stuff

        self.vertex_buffer.bind()
        glVertexPointer(3, GL_FLOAT, 0, None)
        self.normal_buffer.bind()
        glNormalPointer(GL_FLOAT, 0, None)

        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)

        glDrawArrays(GL_TRIANGLES, 0, len(self.vertices))

        glDisableClientState(GL_NORMAL_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

        self.normal_buffer.unbind()
        self.vertex_buffer.unbind()

        ### end VBO stuff

        glDisable(GL_LIGHT1)
        glDisable(GL_LIGHT0)

        glPopMatrix()

    def scale(self, factor):
        self.vertices *= factor

    def display(self):
        glEnable(GL_LIGHTING)
        self.draw_facets()
        glDisable(GL_LIGHTING)

