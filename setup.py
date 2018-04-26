from distutils.spawn import find_executable
from distutils.cmd import Command
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext

import re
import os
import platform
import subprocess
import fnmatch
import distutils.command.build

import sys
IN_PYTHON3 = sys.version_info[0] >= 3
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if IN_PYTHON3:
    sys.path.append(os.path.join(SCRIPT_DIR, os.path.pardir))
    import translate

# Change these to the correct paths
C2RUST_DIR = os.path.realpath(os.path.join(SCRIPT_DIR, os.path.pardir,
                                           os.path.pardir, os.path.pardir))
cc_wrapper_path = C2RUST_DIR + "/cross-checks/c-checks/clang-plugin/cc_wrapper.sh"
cc_path         = C2RUST_DIR + "/dependencies/llvm-6.0.0/build.{}/bin/clang".format(platform.uname()[1])
plugin_path     = C2RUST_DIR + "/cross-checks/c-checks/clang-plugin/build/plugin/CrossChecks.so"
runtime_path    = C2RUST_DIR + "/cross-checks/c-checks/clang-plugin/build/runtime/libruntime.a"
fakechecks_path = C2RUST_DIR + "/cross-checks/libfakechecks"
clevrbuf_path   = C2RUST_DIR + "/cross-checks/ReMon/libclevrbuf"

plugin_args = ['-Xclang', '-plugin-arg-crosschecks',
               '-Xclang', '-C../snudown_c.c2r',
               '-ffunction-sections',  # Used by --icf
               ]

def c_files_in(directory):
    paths = []
    names = os.listdir(directory)
    for f in fnmatch.filter(names, '*.c'):
        paths.append(os.path.join(directory, f))
    return paths


def process_gperf_file(gperf_file, output_file):
    if not find_executable("gperf"):
        raise Exception("Couldn't find `gperf`, is it installed?")
    subprocess.check_call(["gperf", gperf_file, "--output-file=%s" % output_file])

'''
extensions[0] -> extension for translating to rust
extensions[1] -> extension for translating and running rust xcheck
extensions[2] -> extension for running clang xcheck

extensions = [
    Extension(
        name='snudown',
        sources=['snudown.c', 'src/bufprintf.c'] + c_files_in('html/'),
        include_dirs=['src', 'html'],
        libraries=['c2rust_build'],
        library_dirs=['c2rust-build/target/debug']
    ),
    Extension(
        name='snudown',
        sources=['snudown.c', 'src/bufprintf.c'] + c_files_in('html/'),
        include_dirs=['src', 'html'],
        #libraries=['c2rust_build', 'fakechecks'],
        libraries=['c2rust_build', 'clevrbuf'],
        library_dirs=['c2rust_build/target/debug', fakechecks_path, clevrbuf_path],
        extra_link_args=['-Wl,-rpath,{},-rpath,{}'.format(fakechecks_path, clevrbuf_path)],
    ),
    Extension(
        name='snudown',
        sources=['snudown.c', '../xchecks.c'] + c_files_in('src/') + c_files_in('html/'),
        include_dirs=['src', 'html'],
        library_dirs=[fakechecks_path, clevrbuf_path],
        #libraries=["fakechecks"],
        libraries=["clevrbuf"],
        extra_compile_args=plugin_args,
        extra_link_args=['-fuse-ld=gold', '-Wl,--gc-sections,--icf=safe',
                            '-Wl,-rpath,{},-rpath,{}'.format(fakechecks_path, clevrbuf_path)],
        extra_objects=[runtime_path],
    ),
]
'''

extensions = [
    Extension(
        name='snudown',
        sources=['snudown.c'] + c_files_in('src/') + c_files_in('html/'),
        include_dirs=['src', 'html']
    )
]

version = None
version_re = re.compile(r'^#define\s+SNUDOWN_VERSION\s+"([^"]+)"$')
with open('snudown.c', 'r') as f:
    for line in f:
        m = version_re.match(line)
        if m:
            version = m.group(1)
assert version


class BuildSnudown(distutils.command.build.build):
    user_options = distutils.command.build.build.user_options + [
    ('translate', None,
    'translate from c to rust'),

    ('rust-crosschecks', None,
    'translate then run rust crosschecks'),
    ('clang-crosschecks', None,
    'translate then run clang crosschecks'),

    ('use-fakechecks', None,
    'use the fakechecks library to print the cross-checks'),
    ]

    def build_extension(self):
        sources = ['snudown.c']
        sources.extend(c_files_in('html/'))
        libraries = []
        library_dirs= []
        extra_compile_args = []
        extra_link_args = []
        extra_objects=[]

        extensions.pop()
        if self.translate is not None:
            sources.append('src/bufprintf.c')
            library_dirs.append('c2rust-build/target/debug')
            libraries.append('c2rust_build')

        if self.rust_crosschecks is not None:
            sources.append('src/bufprintf.c')
            library_dirs.extend(['c2rust-build/target/debug', fakechecks_path, clevrbuf_path])
            if self.use_fakechecks is not None:
                libraries.extend(['c2rust_build', 'fakechecks'])
            else:
                libraries.extend(['c2rust_build', 'clevrbuf'])
            holder = ['-Wl,-rpath,{},-rpath,{}'.format(fakechecks_path, clevrbuf_path)]
            extra_link_args.extend(holder)

        if self.clang_crosschecks is not None:
            # Set the compiler path to cc_wrapper.sh
            os.environ["CC"] = "{cc_wrapper} {cc} {plugin}".format(
                    cc_wrapper=cc_wrapper_path, cc=cc_path, plugin=plugin_path)
            sources.append('../xchecks.c')
            sources.extend(c_files_in('src/'))
            library_dirs.extend([fakechecks_path, clevrbuf_path])
            if self.use_fakechecks is not None:
                libraries.append('fakechecks')
            else:
                libraries.append('clevrbuf')
            extra_compile_args.extend(plugin_args)
            extra_link_args.extend(['-fuse-ld=gold', '-Wl,--gc-sections,--icf=safe',
                                '-Wl,-rpath,{},-rpath,{}'.format(fakechecks_path, clevrbuf_path)])
            extra_objects.append(runtime_path)

        return Extension(
            name='snudown',
            sources=sources,
            include_dirs=['src', 'html'],
            library_dirs=library_dirs,
            libraries=libraries,
            extra_compile_args=extra_compile_args,
            extra_link_args=extra_link_args,
            extra_objects=extra_objects,
        )

    def initialize_options(self, *args, **kwargs):
        self.translate = self.rust_crosschecks = self.clang_crosschecks = None
        self.use_fakechecks = None
        distutils.command.build.build.initialize_options(self, *args, **kwargs)

    def run(self, *args, **kwargs):
        if self.translate is not None:
            # subprocess.check_call(["../translate.sh", "translate"])
            if IN_PYTHON3:
                translate.main(xcheck=False, snudown=SCRIPT_DIR)
            else:
                subprocess.check_call(["python3", "../translate.py",
                                       "translate", SCRIPT_DIR])
            extensions.append(self.build_extension())

        if self.rust_crosschecks is not None:
            # subprocess.check_call(["../translate.sh", "rustcheck"])
            if IN_PYTHON3:
                translate.main(xcheck=True, snudown=SCRIPT_DIR)
            else:
                subprocess.check_call(["python3", "../translate.py",
                                       "rustcheck", SCRIPT_DIR])
            extensions.append(self.build_extension())

        if self.clang_crosschecks is not None:
            # subprocess.check_call(["../translate.sh"])
            if IN_PYTHON3:
                translate.generate_html_entries_header(snudown=SCRIPT_DIR)
            else:
                subprocess.check_call(["python3", "../translate.py",
                                       "html_entities", SCRIPT_DIR])
            extensions.append(self.build_extension())

        distutils.command.build.build.run(self, *args, **kwargs)


class GPerfingBuildExt(build_ext):
    def run(self):
        #translate.py builds this manually
        #process_gperf_file("src/html_entities.gperf", "src/html_entities.h")
        build_ext.run(self)

setup(
    name='snudown',
    version=version,
    author='Vicent Marti',
    author_email='vicent@github.com',
    license='MIT',
    test_suite="test_snudown.test_snudown",
    cmdclass={'build': BuildSnudown, 'build_ext': GPerfingBuildExt},
    ext_modules=extensions,
)
