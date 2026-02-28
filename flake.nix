{
  description = "Front 1: MEMS Infrastructure – IEEE 2030.7-2017 (Kisengo Microgrid)";

  inputs = {
    # Using the universal HTTPS tarball scheme so it works on any Nix version
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1.tar.gz";

    flake-parts = {
      url = "https://flakehub.com/f/hercules-ci/flake-parts/0.1.tar.gz";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };
  };


  outputs = inputs @ { flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      perSystem =
        { pkgs, ... }: {
          devShells.default = pkgs.mkShell {
            name = "econ-mems";

            packages = with pkgs; [
              nodejs_22
              uv
              python312
              
              (writeShellScriptBin "run-all-tests" ''
                set -e
                echo "=== npm tests ==="
                npm run test
                echo ""
                echo "=== pytest ==="
                uv run pytest
              '')
            ];

            # Fix for pre-compiled Python wheels (numpy, pandas, etc.)
            # Exposes basic C libraries so dynamically linked wheels work
            env.LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
              pkgs.stdenv.cc.cc.lib
              pkgs.zlib
            ];

            shellHook = ''
              # Tell uv to use the project directory for its virtualenv
              export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
              
              # Guard network operations: only run if directories don't exist.
              # If you need to update packages, run `uv sync` or `npm install` manually.
              if [ ! -d "$UV_PROJECT_ENVIRONMENT" ]; then
                echo "Bootstrapping uv virtual environment..."
                uv sync --all-extras
              fi

              if [ ! -d "node_modules" ]; then
                echo "Bootstrapping node_modules..."
                npm install
              fi
            '';
          };
        };
    };
}

