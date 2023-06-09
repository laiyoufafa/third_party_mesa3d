# Copyright © 2020 Google, Inc

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

afuc_parser = custom_target(
  'parser.[ch]',
  input: 'parser.y',
  output: ['parser.c', 'parser.h'],
  command: [
    prog_bison, '@INPUT@', '--defines=@OUTPUT1@', '--output=@OUTPUT0@'
  ]
)

afuc_lexer = custom_target(
  'lexer.c',
  input: 'lexer.l',
  output: 'lexer.c',
  command: [
    prog_flex, '-o', '@OUTPUT@', '@INPUT@'
  ]
)

asm = executable(
  'afuc-asm',
  [
    'asm.c',
    'util.c',
    'util.h',
    afuc_lexer,
    afuc_parser,
  ],
  include_directories: [
    inc_freedreno_rnn, inc_include, inc_src, inc_util,
  ],
  link_with: [
    libfreedreno_rnn,
  ],
  dependencies: [],
  build_by_default : with_tools.contains('freedreno'),
  install: install_fd_decode_tools,
)

disasm = executable(
  'afuc-disasm',
  [
    'disasm.c',
    'emu.c',
    'emu.h',
    'emu-ds.c',
    'emu-regs.c',
    'emu-ui.c',
    'util.c',
    'util.h',
  ],
  include_directories: [
    inc_freedreno,
    inc_freedreno_rnn,
    inc_include,
    inc_src,
    inc_util,
  ],
  link_with: [
    libfreedreno_rnn,
  ],
  dependencies: [
  ],
  build_by_default : with_tools.contains('freedreno'),
  install: install_fd_decode_tools,
)

if with_tests
  diff = find_program('diff')

  disasm_fw = custom_target('afuc_test.asm',
    output: 'afuc_test.asm',
    command: [disasm, '-u', files('../.gitlab-ci/reference/afuc_test.fw'), '-g', '630'],
    capture: true
  )
  test('afuc-disasm',
    diff,
    args: ['-u', files('../.gitlab-ci/reference/afuc_test.asm'), disasm_fw],
    suite: 'freedreno',
    workdir: meson.source_root()
  )

  asm_fw = custom_target('afuc_test.fw',
    output: 'afuc_test.fw',
    command: [asm, '-g', '6', files('../.gitlab-ci/traces/afuc_test.asm'), '@OUTPUT@'],
  )
  test('afuc-asm',
    diff,
    args: ['-u', files('../.gitlab-ci/reference/afuc_test.fw'), asm_fw],
    suite: 'freedreno',
    workdir: meson.source_root()
  )
endif
