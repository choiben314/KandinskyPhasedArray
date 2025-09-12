prj_project new -name "michub" -impl "impl" -dev LFE5U-25F-6BG381C -synthesis "synplify"
prj_impl option {include path} {""}
prj_src add "/Users/benchoi/Projects/KandinskyPhasedArray/cores/pdm_core.v" -work work
prj_src add "/Users/benchoi/Projects/KandinskyPhasedArray/build/gateware/michub.v" -work work
prj_impl option top "michub"
prj_project save
prj_run Synthesis -impl impl -forceOne
prj_run Translate -impl impl
prj_run Map -impl impl
prj_run PAR -impl impl
prj_run Export -impl impl -task Bitgen
prj_project close