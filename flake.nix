{
  description = "Front 1: MEMS Infrastructure – IEEE 2030.7-2017 (Kisengo Microgrid)";

  inputs = {
    # Pin nixpkgs via FlakeHub for reproducibility
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1";

    # flake-parts: modular flake output composition
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };

    # devenv: declarative developer environments
    devenv = {
      url = "github:cachix/devenv";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # uv2nix: parse uv.lock and produce Nix Python environments
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # pyproject-nix: low-level PEP 517/518 support for Nix
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # Build-system derivations for uv2nix wheels
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs @ { flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [ inputs.devenv.flakeModule ];

      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      perSystem =
        { config
        , self'
        , inputs'
        , pkgs
        , system
        , ...
        }: {
          # ──────────────────────────────────────────────────────────────────
          # Developer shell (entered via `nix develop`)
          # ──────────────────────────────────────────────────────────────────
          devenv.shells.default = {
            name = "econ-mems";

            packages = with pkgs; [
              # Node.js runtime for XState / TypeScript tooling
              nodejs_22
              # uv for Python package management (uv2nix-compatible)
              uv
            ];

            # Python 3.12 managed via uv (uv2nix parses uv.lock)
            languages.python = {
              enable = true;
              uv = {
                enable = true;
                # Sync all dependency groups (including dev) on shell entry
                sync = {
                  enable = true;
                  allExtras = true;
                };
              };
            };

            # JavaScript / Node.js – npm install on shell entry
            languages.javascript = {
              enable = true;
              package = pkgs.nodejs_22;
              npm.install.enable = true;
            };

            # Convenience: run both test suites from the shell
            scripts.run-all-tests.exec = ''
              set -e
              echo "=== npm tests ==="
              npm run test
              echo ""
              echo "=== pytest ==="
              pytest
            '';
          };
        };
    };
}
