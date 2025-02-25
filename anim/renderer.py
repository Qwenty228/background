import pygame as pg
import pygame.freetype
from array import array
import moderngl
import win32gui
import importlib
from typing import Literal
import logging
import argparse
import os
import glob
from PIL import Image

from utils.worker import Worker
from utils.settings import *


class Renderer:
    def __init__(self, debug) -> None:
        pg.freetype.init()
        self.debug = debug
        self.font = pg.freetype.SysFont('Arial', 30)

        self.__clipped = False
        self.wm = Worker()
        self.wm.get_workerw()

        self.time = 0
        self.running = True

        self.make_th = None
        self.choose_anim()

    def __clip_surface(self):
        pg.display.set_mode((0, 0), pg.HIDDEN | pg.OPENGL |
                            pg.DOUBLEBUF | pg.NOFRAME | pg.SRCALPHA)
        pg.display.set_mode((0, 0), pg.SHOWN | pg.OPENGL |
                            pg.DOUBLEBUF | pg.NOFRAME | pg.SRCALPHA)
        win32gui.SetParent(pg.display.get_wm_info()['window'], self.wm.WorkerW)

    def surf2tex(self, surf: pg.Surface, ctx: moderngl.Context,  mode: Literal['clear', 'image'] = 'image'):
        tex = ctx.texture(surf.get_size(), 4)  # number of color channels
        if mode != 'clear':
            # no interpolation
            tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
            tex.swizzle = 'BGRA'  # gl differs from pygame, so we have to swizzle the colors
        tex.write(surf.get_view('1'))  # write the surface to the texture
        return tex

    def choose_anim(self, path: str = "shaders.circular"):
        self.animation_name = path
        if 'data' not in path:
            path = f'data.{path}'
        module = importlib.import_module(path)
        self.animation = module.Anim()

    def get_vao(self, ctx, quad_buffer, animation):
        program = ctx.program(vertex_shader=vert_shader,
                              fragment_shader=animation.frag_shader)
        vao = ctx.vertex_array(
            program, [(quad_buffer, '2f 2f', 'vert', 'texcoord')]
        )
        return program, vao

    def animate(self):
        self.__clip_surface()
        current_animation = self.animation

        ctx = moderngl.create_context()
        quad_buffer = ctx.buffer(data=array('f', [
            -1.0,  1.0, 0.0, 0.0,   # top left
            1.0, 1.0, 1.0, 0.0,     # top right
            -1.0,  -1.0, 0.0, 1.0,  # bottom left
            1.0, -1.0, 1.0, 1.0,   # bottom right
        ]))

        program, vao = self.get_vao(ctx, quad_buffer, current_animation)

        clock = pg.time.Clock()
        window = pg.display.get_surface()
        aspect_ratio = window.get_width()/window.get_height()
        display = pg.Surface((WIDTH * aspect_ratio, HEIGHT))

        pg.event.pump()

        interval = 2
        pause = False
        while self.running:
            display.fill('black')

            dt = clock.tick(FPS)*0.001
            self.time += dt
            interval -= dt
            if interval < 0:
                interval = 2
                try:
                    with open("anim/anim.txt", 'r') as f:
                        new_anim = f.read().strip()
                    if new_anim != self.animation_name:
                        logging.info(f"New animation selected: {new_anim}")
                        self.choose_anim(new_anim)

                        current_animation = self.animation
                        program, vao = self.get_vao(
                            ctx, quad_buffer, current_animation)

                except FileNotFoundError as e:
                    logging.error(e)

                pause = self.wm.is_foreground_window_fullscreen()
                if pause:
                    self.wm.hide_workerw()
                    continue
                else:
                    self.wm.show_workerw()

            img = current_animation.update(surf=display, dt=dt,
                                           aspect_ratio=aspect_ratio)
            if img:
                display = img

            if self.make_th:
                if self.time > 3:
                    logging.info(f"Making thumbnail: {self.make_th}")
                    # pg.image.save(display, f"anim/data/images/{self.make_th}.png")
                    # pixels = frame_tex.read()
                    # image = Image.frombytes('RGB', (HEIGHT, WIDTH), pixels)

                    # # Save the frame to a PNG file
                    # image.save(f"anim/data/images/{self.make_th}.png")

                    self.make_th = None

            if self.debug:
                self.font.render_to(
                    display, (0.5*WIDTH*aspect_ratio, 0), f'FPS: {clock.get_fps():.2f}', 'white')
                frame_tex = self.surf2tex(display, ctx)
            else:
                frame_tex = self.surf2tex(display, ctx, current_animation.mode)

            frame_tex.use(0)
            program['tex'] = 0
            current_animation.set_uniforms(
                program, time=self.time, aspect_ratio=aspect_ratio)
            vao.render(mode=moderngl.TRIANGLE_STRIP)

            pg.display.flip()
            frame_tex.release()


def check_thumbnails(filename: str):
    # Define the folder where the images are stored
    image_folder = 'anim/data/images'

    return glob.glob(os.path.join(image_folder, f'{filename}.*'))


if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        filename='wallpaper_engine.log',  # Log to a file
        level=logging.INFO,  # Set logging level
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    logging.info("Starting engine")

    parser = argparse.ArgumentParser(prog='Wallpaper Engine',
                                     description='A wallpaper engine for Windows, powered by Tkinter and Pygame.',
                                     epilog='Enjoy the wallpaper engine!')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Enable debug mode')
    parser.add_argument("-a", "--animation", type=str,
                        default="shaders.circular")
    parser.add_argument("-c", "--clear", action="store_true")

    args = parser.parse_args()

    renderer = Renderer(debug=args.debug)

    if args.clear:
        renderer.wm.kill_workerw()
    else:
        renderer.choose_anim(args.animation)
        try:
            fn = args.animation.replace('.', '_')
            # if not check_thumbnails(fn):
            # renderer.make_th = fn
            logging.info(f"thumbnail: {fn}")
        except Exception as e:
            logging.error(e)

        renderer.animate()
