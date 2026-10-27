// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <map>
#include <string>

#include "App/ProgramInformation.h"

using Config = std::map<std::string, std::string>;

static Config baseConfig()
{
    return {
        {"BuildVersionMajor", "26"},
        {"BuildVersionMinor", "3"},
        {"BuildVersionPoint", "0"},
        {"BuildVersionSuffix", ""},
    };
}

TEST(ProgramInformation, versionStringIsFreeCADVersionWithoutRelease)
{
    auto config = baseConfig();
    EXPECT_EQ(App::ProgramInformation::versionString(config), "26.3.0");
    config["BuildVersionBuild"] = "0";
    EXPECT_EQ(App::ProgramInformation::versionString(config), "26.3.0");
}

TEST(ProgramInformation, versionStringAppendsOtherCADRelease)
{
    auto config = baseConfig();
    config["BuildVersionBuild"] = "2";
    EXPECT_EQ(App::ProgramInformation::versionString(config), "26.3.0.2");
}

TEST(ProgramInformation, versionStringKeepsSuffixLast)
{
    auto config = baseConfig();
    config["BuildVersionBuild"] = "2";
    config["BuildVersionSuffix"] = "dev";
    EXPECT_EQ(App::ProgramInformation::versionString(config), "26.3.0.2dev");
}
