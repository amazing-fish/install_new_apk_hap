# Faster 9-slice image elements for image-based ttk themes (sv-ttk) on Windows.
#
# ttk draws a stretched image element by tiling its middle region; each tile is
# a separate Tk_RedrawImage call, and on Windows every call on an image with
# alpha reads back and blends the destination. sv-ttk's sprites are ~20 px, so
# a wide entry repaints with hundreds of calls. While the theme is sourced this
# wrapper records image elements, pins their natural size (-width/-height of
# the original sprite), and afterwards widens the stretch axes of sprites that
# are only ever used by bordered, stretched elements, by repeating their centre
# column/row. The middle of a 9-slice sprite is uniform along its stretch axis,
# so the drawn result is unchanged; only the number of tiles drops.

namespace eval ::ttk_tile_fix {
    variable uses [dict create]   ;# image -> list of allowed axis sets ({} = never widen)
}

proc ::ttk_tile_fix::padding {border} {
    lassign $border l t r b
    if {$t eq ""} {set t $l}
    if {$r eq ""} {set r $l}
    if {$b eq ""} {set b $t}
    return [list $l $t $r $b]
}

proc ::ttk_tile_fix::style {args} {
    variable uses
    if {[lrange $args 0 1] eq {element create} && [lindex $args 3] eq "image"} {
        set spec [lindex $args 4]
        set options [lrange $args 5 end]
        set images [list [lindex $spec 0]]
        foreach {_state image} [lrange $spec 1 end] {lappend images $image}
        set axes {}
        if {[dict exists $options -border]} {
            set sticky [expr {[dict exists $options -sticky] ? [dict get $options -sticky] : "nsew"}]
            lassign [padding [dict get $options -border]] l t r b
            foreach image $images {
                set w [image width $image]
                set h [image height $image]
                set cx [expr {$w / 2}]
                set cy [expr {$h / 2}]
                set ok {}
                if {[string match *e* $sticky] && [string match *w* $sticky] && $l <= $cx && $r < $w - $cx} {
                    lappend ok x
                }
                if {[string match *n* $sticky] && [string match *s* $sticky] && $t <= $cy && $b < $h - $cy} {
                    lappend ok y
                }
                dict lappend uses $image $ok
            }
            # Pin the natural size to the sprite, so widening cannot change it.
            set base [lindex $images 0]
            if {![dict exists $options -width]} {lappend args -width [image width $base]}
            if {![dict exists $options -height]} {lappend args -height [image height $base]}
        } else {
            foreach image $images {dict lappend uses $image {}}
        }
    }
    uplevel 1 [list ::ttk_tile_fix::original_style {*}$args]
}

proc ::ttk_tile_fix::widen {image axis target} {
    set w [image width $image]
    set h [image height $image]
    set size [expr {$axis eq "x" ? $w : $h}]
    set extra [expr {$target - $size}]
    if {$extra <= 0} return
    set copy [image create photo]
    $copy copy $image -compositingrule set
    $image blank
    set centre [expr {$size / 2}]
    if {$axis eq "x"} {
        $image configure -width [expr {$w + $extra}] -height $h
        $image copy $copy -from 0 0 $centre $h -to 0 0 -compositingrule set
        $image copy $copy -from $centre 0 [expr {$centre + 1}] $h \
            -to $centre 0 [expr {$centre + $extra + 1}] $h -compositingrule set
        $image copy $copy -from [expr {$centre + 1}] 0 $w $h \
            -to [expr {$centre + $extra + 1}] 0 -compositingrule set
    } else {
        $image configure -width $w -height [expr {$h + $extra}]
        $image copy $copy -from 0 0 $w $centre -to 0 0 -compositingrule set
        $image copy $copy -from 0 $centre $w [expr {$centre + 1}] \
            -to 0 $centre $w [expr {$centre + $extra + 1}] -compositingrule set
        $image copy $copy -from 0 [expr {$centre + 1}] $w $h \
            -to 0 [expr {$centre + $extra + 1}] -compositingrule set
    }
    image delete $copy
}

# Source `script` with the wrapper installed, then widen what is safe to widen.
# Only the sprites of `sprites` (an array of image names, e.g. the light
# theme's) are widened, so the unused theme costs no extra memory.
proc ::ttk_tile_fix::source_theme {script sprites width height} {
    variable uses
    set uses [dict create]
    rename ::ttk::style ::ttk_tile_fix::original_style
    proc ::ttk::style {args} {uplevel 1 [list ::ttk_tile_fix::style {*}$args]}
    try {
        uplevel #0 [list source $script]
    } finally {
        rename ::ttk::style {}
        rename ::ttk_tile_fix::original_style ::ttk::style
    }
    upvar #0 $sprites images
    set keep [lmap {name image} [array get images] {set image}]
    set widened 0
    dict for {image axis_sets} $uses {
        if {$image ni $keep} continue
        set axes {}
        foreach axis {x y} {
            set everywhere 1
            foreach allowed $axis_sets {
                if {$axis ni $allowed} {set everywhere 0}
            }
            if {$everywhere} {lappend axes $axis}
        }
        foreach axis $axes {
            widen $image $axis [expr {$axis eq "x" ? $width : $height}]
        }
        if {$axes ne {}} {incr widened}
    }
    return $widened
}
