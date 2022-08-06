{ lib
, buildPythonApplication
, aiohttp
, jsonschema
, systemd
, black
, flake8
, mypy
}:

buildPythonApplication {
  pname = "limdberator";
  version = "0.0.0";

  src = ./.;

  propagatedBuildInputs = [
    aiohttp
    jsonschema
    systemd
  ];

  nativeBuildInputs = [
    black
    flake8
    mypy
  ];

  pythonImportsCheck = [ "limdberator" ];

  meta = with lib; {
    description = "Receive and store data scraped by LIMDberator.";
    license = licenses.gpl2Plus;
    maintainers = with maintainers; [ schnusch ];
  };
}
