// Universal bootstrap, shared by module Core Worker and classic robot Worker.
self.tankbotPython = async function(bundleURL, trusted, loader, onOutput=null) {
  const py = await loader({indexURL:"/pyodide/", stdout:line=>onOutput?.(line), stderr:line=>onOutput?.(line)});
  if(trusted) await py.loadPackage("jsonschema");
  await py.loadPackage("numpy");
  const bundle = await (await fetch(bundleURL)).json();
  for(const [relative,source] of Object.entries(bundle)) {
    const path="/tankbot/"+relative;
    py.FS.mkdirTree(path.slice(0,path.lastIndexOf("/")));
    py.FS.writeFile(path,source);
  }
  py.runPython("import sys, json\nsys.path[:0]=['/tankbot/host','/tankbot/protocol','/tankbot/sdk/python','/tankbot/runtime']");
  return py;
};
