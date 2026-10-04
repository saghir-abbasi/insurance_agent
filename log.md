==== Application Startup at 2026-10-03 19:09:48 =====

   Building insurance-agent @ file:///workspace
      Built insurance-agent @ file:///workspace
Uninstalled 1 package in 0.78ms
Installed 1 package in 7ms
2026-10-03 19:10:05,940 - insurance_agent.core.realtime_reasoning - INFO - Realtime reasoning effort patch applied (REALTIME_REASONING_EFFORT=low)
2026-10-03 19:10:06 - Created default translation directory at /workspace/.chainlit/translations
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/bn.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/de-DE.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/el-GR.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/en-US.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/es.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/fr-FR.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/gu.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/he-IL.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/hi.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/it.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/ja.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/kn.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/ko.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/ml.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/mr.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/nl.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/ta.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/te.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/zh-CN.json
2026-10-03 19:10:06 - Created default translation file at /workspace/.chainlit/translations/zh-TW.json
Traceback (most recent call last):
  File "/workspace/.venv/bin/uvicorn", line 10, in <module>
    sys.exit(main())
             ^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/click/core.py", line 1485, in __call__
    return self.main(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/click/core.py", line 1406, in main
    rv = self.invoke(ctx)
         ^^^^^^^^^^^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/click/core.py", line 1269, in invoke
    return ctx.invoke(self.callback, **ctx.params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/click/core.py", line 824, in invoke
    return callback(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/main.py", line 423, in main
    run(
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/main.py", line 593, in run
    server.run()
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/server.py", line 67, in run
    return asyncio_run(self.serve(sockets=sockets), loop_factory=self.config.get_loop_factory())
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "uvloop/loop.pyx", line 1518, in uvloop.loop.Loop.run_until_complete
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/server.py", line 71, in serve
    await self._serve(sockets)
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/server.py", line 78, in _serve
    config.load()
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/config.py", line 439, in load
    self.loaded_app = import_from_string(self.app)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/importer.py", line 19, in import_from_string
    module = importlib.import_module(module_str)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/importlib/__init__.py", line 90, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap>", line 1387, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1360, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1331, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 935, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/workspace/src/insurance_agent/main.py", line 70, in <module>
    mount_chainlit(app=app, target="src/insurance_agent/app.py", path="/app")
  File "/workspace/.venv/lib/python3.12/site-packages/chainlit/utils.py", line 149, in mount_chainlit
    load_module(config.run.module_name)
  File "/workspace/.venv/lib/python3.12/site-packages/chainlit/config.py", line 569, in load_module
    spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/workspace/src/insurance_agent/app.py", line 11, in <module>
    from chainlit.cli import run_chainlit
  File "/workspace/.venv/lib/python3.12/site-packages/chainlit/cli/__init__.py", line 9, in <module>
    nest_asyncio.apply()
  File "/workspace/.venv/lib/python3.12/site-packages/nest_asyncio.py", line 19, in apply
    _patch_loop(loop)
  File "/workspace/.venv/lib/python3.12/site-packages/nest_asyncio.py", line 193, in _patch_loop
    raise ValueError('Can\'t patch loop of type %s' % type(loop))
ValueError: Can't patch loop of type <class 'uvloop.Loop'>
   Building insurance-agent @ file:///workspace
      Built insurance-agent @ file:///workspace
Uninstalled 1 package in 1ms
Installed 1 package in 8ms
2026-10-03 19:10:15,073 - insurance_agent.core.realtime_reasoning - INFO - Realtime reasoning effort patch applied (REALTIME_REASONING_EFFORT=low)
2026-10-03 19:10:16 - Created default translation directory at /workspace/.chainlit/translations
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/bn.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/de-DE.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/el-GR.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/en-US.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/es.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/fr-FR.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/gu.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/he-IL.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/hi.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/it.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/ja.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/kn.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/ko.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/ml.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/mr.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/nl.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/ta.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/te.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/zh-CN.json
2026-10-03 19:10:16 - Created default translation file at /workspace/.chainlit/translations/zh-TW.json
Traceback (most recent call last):
  File "/workspace/.venv/bin/uvicorn", line 10, in <module>
    sys.exit(main())
             ^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/click/core.py", line 1485, in __call__
    return self.main(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/click/core.py", line 1406, in main
    rv = self.invoke(ctx)
         ^^^^^^^^^^^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/click/core.py", line 1269, in invoke
    return ctx.invoke(self.callback, **ctx.params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/click/core.py", line 824, in invoke
    return callback(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/main.py", line 423, in main
    run(
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/main.py", line 593, in run
    server.run()
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/server.py", line 67, in run
    return asyncio_run(self.serve(sockets=sockets), loop_factory=self.config.get_loop_factory())
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "uvloop/loop.pyx", line 1518, in uvloop.loop.Loop.run_until_complete
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/server.py", line 71, in serve
    await self._serve(sockets)
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/server.py", line 78, in _serve
    config.load()
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/config.py", line 439, in load
    self.loaded_app = import_from_string(self.app)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/.venv/lib/python3.12/site-packages/uvicorn/importer.py", line 19, in import_from_string
    module = importlib.import_module(module_str)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/importlib/__init__.py", line 90, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap>", line 1387, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1360, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1331, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 935, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/workspace/src/insurance_agent/main.py", line 70, in <module>
    mount_chainlit(app=app, target="src/insurance_agent/app.py", path="/app")
  File "/workspace/.venv/lib/python3.12/site-packages/chainlit/utils.py", line 149, in mount_chainlit
    load_module(config.run.module_name)
  File "/workspace/.venv/lib/python3.12/site-packages/chainlit/config.py", line 569, in load_module
    spec.loader.exec_module(module)
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/workspace/src/insurance_agent/app.py", line 11, in <module>
    from chainlit.cli import run_chainlit
  File "/workspace/.venv/lib/python3.12/site-packages/chainlit/cli/__init__.py", line 9, in <module>
    nest_asyncio.apply()
  File "/workspace/.venv/lib/python3.12/site-packages/nest_asyncio.py", line 19, in apply
    _patch_loop(loop)
  File "/workspace/.venv/lib/python3.12/site-packages/nest_asyncio.py", line 193, in _patch_loop
    raise ValueError('Can\'t patch loop of type %s' % type(loop))
ValueError: Can't patch loop of type <class 'uvloop.Loop'>
