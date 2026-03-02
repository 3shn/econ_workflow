{ pkgs, ... }:
{
  home.username = "u";
  home.homeDirectory = "/home/u";
  home.stateVersion = "25.05";

  programs.home-manager.enable = true;

  home.packages = with pkgs; [
    opentofu
  ];
}
